"""Portfolio returns service — computes IRR across time horizons."""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Account, DailyHoldingValue
from models.account_snapshot import AccountSnapshot
from models.activity import Activity
from models.sync_session import SyncSession

logger = logging.getLogger(__name__)

DEFAULT_PERIODS = ["1D", "1M", "3M", "YTD", "1Y", "3Y", "LQ", "LY"]


@dataclass
class ReturnResult:
    """Return calculation for a single time period."""

    period: str  # "1D", "1M", etc.
    irr: Decimal | None
    start_date: date
    end_date: date
    start_value: Decimal
    end_value: Decimal
    has_sufficient_data: bool


@dataclass
class ScopeReturns:
    """Returns for a single scope (portfolio or account)."""

    scope_id: str  # "portfolio" or account UUID
    scope_name: str
    periods: list[ReturnResult] = field(default_factory=list)


@dataclass
class PortfolioReturnsResult:
    """Top-level result combining portfolio and account returns."""

    portfolio: ScopeReturns | None = None
    accounts: list[ScopeReturns] = field(default_factory=list)


class PortfolioReturnsService:
    """Computes money-weighted returns (IRR)."""

    def get_returns(
        self,
        db: Session,
        scope: str = "all",
        periods: list[str] | None = None,
        include_inactive: bool = False,
        account_ids: list[str] | None = None,
    ) -> PortfolioReturnsResult:
        """Single entry point for return calculations.

        Args:
            db: Database session.
            scope: "all" (portfolio + accounts), "portfolio", or an account UUID.
            periods: List of period strings. Defaults to DEFAULT_PERIODS.
            include_inactive: If True, include inactive accounts in the
                all-accounts list. Portfolio-level always excludes inactive
                and include_in_allocation=False accounts regardless.
            account_ids: If provided, restrict portfolio-level returns to
                these account IDs (intersected with allocation accounts).
        """
        periods = periods or DEFAULT_PERIODS
        result = PortfolioReturnsResult()

        if scope == "all":
            result.portfolio = self.get_portfolio_returns(
                db, periods, account_ids=account_ids,
            )
            result.accounts = self.get_all_account_returns(
                db, periods, include_inactive=include_inactive,
                account_ids=account_ids,
            )
        elif scope == "portfolio":
            result.portfolio = self.get_portfolio_returns(
                db, periods, account_ids=account_ids,
            )
        else:
            # Treat scope as account_id
            result.accounts = [self.get_account_returns(db, scope, periods)]

        return result

    def get_portfolio_returns(
        self,
        db: Session,
        periods: list[str],
        account_ids: list[str] | None = None,
    ) -> ScopeReturns:
        """Compute returns across all allocation accounts (portfolio-level).

        Includes both active and inactive accounts with include_in_allocation=True.
        Inactive accounts (e.g. a SimpleFIN account superseded by Plaid) still
        contributed real historical value and cash flows, so excluding them would
        silently corrupt returns for any period that overlaps their history.
        Their closing $0 DHV sentinel naturally prevents double-counting after
        the deactivation date.

        When account_ids is provided, results are further restricted to that subset.
        """
        query = db.query(Account).filter(
            Account.include_in_allocation.is_(True),
        )
        if account_ids is not None:
            query = query.filter(Account.id.in_(account_ids))
        filtered_ids = [acc.id for acc in query.all()]
        return self._compute_scope_returns(
            db, periods, scope_id="portfolio", scope_name="Portfolio",
            account_ids=filtered_ids,
        )

    def get_account_returns(
        self, db: Session, account_id: str, periods: list[str],
    ) -> ScopeReturns:
        """Compute returns for a single account (no filtering)."""
        account = db.query(Account).filter(Account.id == account_id).first()
        name = account.name if account else "Unknown"
        return self._compute_scope_returns(
            db, periods,
            scope_id=account_id, scope_name=name,
            account_ids=[account_id],
        )

    def get_all_account_returns(
        self,
        db: Session,
        periods: list[str],
        include_inactive: bool = False,
        account_ids: list[str] | None = None,
    ) -> list[ScopeReturns]:
        """Compute returns for each account individually.

        Args:
            include_inactive: If True, include inactive accounts.
                Defaults to active accounts only.
            account_ids: If provided, restrict to these account IDs.
        """
        query = db.query(Account)
        if not include_inactive:
            query = query.filter(Account.is_active.is_(True))
        if account_ids is not None:
            query = query.filter(Account.id.in_(account_ids))
        accounts = query.order_by(Account.name).all()

        results = []
        for acc in accounts:
            results.append(self.get_account_returns(db, acc.id, periods))
        return results

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _compute_scope_returns(
        self,
        db: Session,
        periods: list[str],
        scope_id: str,
        scope_name: str,
        account_ids: list[str] | None = None,
    ) -> ScopeReturns:
        """Compute returns for a given scope across multiple periods."""
        today = date.today()
        end_date = today - timedelta(days=1)  # yesterday = latest complete DHV day

        scope = ScopeReturns(scope_id=scope_id, scope_name=scope_name)

        for period in periods:
            try:
                start, end = self._get_period_dates(period, end_date)
            except ValueError:
                logger.warning("Unknown period %s, skipping", period)
                continue

            daily_values = self._get_daily_values(db, start, end, account_ids)
            cash_flows = self._get_external_cash_flows(db, start, end, account_ids)

            # Infer $0 end value for accounts that were liquidated/emptied.
            # If we have start data but no end data, check whether the latest
            # snapshot(s) for these accounts show a zero total value.
            if start in daily_values and end not in daily_values and account_ids:
                if self._accounts_emptied(db, account_ids, end):
                    daily_values[end] = Decimal("0")
                    logger.info(
                        "Inferred $0 end value for %s on %s (accounts emptied)",
                        scope_name, end,
                    )

            start_value = daily_values.get(start, Decimal("0"))
            end_value = daily_values.get(end, Decimal("0"))

            has_data = start in daily_values and end in daily_values
            irr = None

            if has_data:
                irr = self._compute_xirr(
                    start_value, end_value, cash_flows, start, end,
                )

            scope.periods.append(ReturnResult(
                period=period,
                irr=irr,
                start_date=start,
                end_date=end,
                start_value=start_value,
                end_value=end_value,
                has_sufficient_data=has_data,
            ))

        return scope

    @staticmethod
    def _get_period_dates(period: str, end_date: date) -> tuple[date, date]:
        """Map a period string to (start_date, end_date).

        Start dates use the last day *before* the period (e.g. YTD starts
        Dec 31, QTD starts last day of the prior quarter) because the start
        date's DHV serves as the opening baseline value for return calculation.
        """
        if period == "1D":
            return end_date - timedelta(days=1), end_date
        elif period == "1M":
            return _subtract_months(end_date, 1), end_date
        elif period == "3M":
            return _subtract_months(end_date, 3), end_date
        elif period == "QTD":
            # QTD starts from last day of previous quarter
            return _last_day_of_prev_quarter(end_date), end_date
        elif period == "YTD":
            # YTD starts from last day of previous year
            return date(end_date.year - 1, 12, 31), end_date
        elif period == "1Y":
            return _subtract_months(end_date, 12), end_date
        elif period == "3Y":
            return _subtract_months(end_date, 36), end_date
        elif period == "LQ":
            # Last complete calendar quarter
            q_start, q_end = _last_quarter(end_date)
            return q_start, q_end
        elif period == "LY":
            # Last complete calendar year
            prev_year = end_date.year - 1
            return date(prev_year, 1, 1), date(prev_year, 12, 31)
        else:
            raise ValueError(f"Unknown period: {period}")

    @staticmethod
    def _get_daily_values(
        db: Session,
        start: date,
        end: date,
        account_ids: list[str] | None = None,
    ) -> dict[date, Decimal]:
        """Query DHV table, sum market_value by valuation_date."""
        query = (
            db.query(
                DailyHoldingValue.valuation_date,
                func.sum(DailyHoldingValue.market_value),
            )
            .filter(
                DailyHoldingValue.valuation_date >= start,
                DailyHoldingValue.valuation_date <= end,
            )
        )
        if account_ids is not None:
            query = query.filter(DailyHoldingValue.account_id.in_(account_ids))

        query = query.group_by(DailyHoldingValue.valuation_date)
        rows = query.all()

        return {row[0]: Decimal(str(row[1])) for row in rows}

    @staticmethod
    def _accounts_emptied(
        db: Session,
        account_ids: list[str],
        as_of: date,
    ) -> bool:
        """Check whether all given accounts have been emptied (total_value=0).

        Looks at the most recent successful snapshot for each account on or
        before *as_of*. Returns True only if every account's latest snapshot
        has total_value == 0.
        """
        from datetime import datetime, time, timezone

        as_of_dt = datetime.combine(as_of, time(23, 59, 59), tzinfo=timezone.utc)

        for acct_id in account_ids:
            latest = (
                db.query(AccountSnapshot)
                .join(SyncSession)
                .filter(
                    AccountSnapshot.account_id == acct_id,
                    AccountSnapshot.status == "success",
                    SyncSession.timestamp <= as_of_dt,
                )
                .order_by(SyncSession.timestamp.desc())
                .first()
            )
            if latest is None:
                # No snapshot at all — can't confirm emptied
                return False
            if latest.total_value and latest.total_value != 0:
                return False

        return True

    # Activity types that represent external cash flows.
    # deposit/withdrawal/transfer_in/transfer_out: direction is unambiguous from the type.
    # transfer/receive: direction inferred from amount sign (provider-dependent).
    CASH_FLOW_TYPES = frozenset({
        "deposit", "withdrawal",
        "transfer_in", "transfer_out",
        "transfer", "receive",
    })

    @staticmethod
    def _get_external_cash_flows(
        db: Session,
        start: date,
        end: date,
        account_ids: list[str] | None = None,
    ) -> dict[date, list[Decimal]]:
        """Query Activity for cash-flow-type transactions, return signed amounts by date.

        Sign convention (positive = money entering, negative = money leaving):
        - deposit, transfer_in  → abs(amount), always positive
        - withdrawal, transfer_out → abs(amount), always negative
        - transfer, receive     → amount sign as-is (provider-dependent)
        """
        query = (
            db.query(Activity)
            .filter(
                Activity.type.in_(PortfolioReturnsService.CASH_FLOW_TYPES),
                Activity.amount.isnot(None),
            )
        )

        # Filter by date range using the datetime column
        start_dt = _date_to_start_of_day(start)
        end_dt = _date_to_end_of_day(end)
        query = query.filter(
            Activity.activity_date >= start_dt,
            Activity.activity_date <= end_dt,
        )

        if account_ids is not None:
            query = query.filter(Activity.account_id.in_(account_ids))

        activities = query.all()

        result: dict[date, list[Decimal]] = defaultdict(list)
        for act in activities:
            signed = _signed_cash_flow(act.type, act.amount)
            result[act.activity_date.date()].append(signed)

        return dict(result)

    @staticmethod
    def _compute_xirr(
        start_value: Decimal,
        end_value: Decimal,
        cash_flows: dict[date, list[Decimal]],
        start: date,
        end: date,
    ) -> Decimal | None:
        """Compute cumulative IRR over the period via Newton-Raphson.

        Returns the holding-period return (not annualized). Time fractions
        are normalized to [0, 1] where 1 = the full period length.

        Cash flow convention:
        - Initial investment (start_value) is a negative cash flow (money out)
        - Final value (end_value) is a positive cash flow (money in)
        - Deposits are negative (investor puts money in)
        - Withdrawals are positive (investor takes money out)
        """
        if start_value == 0 and not cash_flows:
            return None

        total_days = (end - start).days
        if total_days <= 0:
            return None

        # Build cash flow list: [(period_fraction, amount), ...]
        # Time is normalized to [0, 1] so the solver returns cumulative return.
        # Start value = money invested (outflow = negative)
        flows: list[tuple[float, float]] = []
        if start_value != 0:
            flows.append((0.0, -float(start_value)))

        for cf_date, amounts in cash_flows.items():
            if cf_date < start or cf_date > end:
                continue
            days_from_start = (cf_date - start).days
            t = days_from_start / total_days
            for amount in amounts:
                # Deposits are positive in our convention (money entering portfolio)
                # but negative for IRR (investor outflow)
                flows.append((t, -float(amount)))

        # End value = money received (inflow = positive)
        flows.append((1.0, float(end_value)))

        if not flows:
            return None

        # Newton-Raphson to solve: sum(cf_i / (1+r)^t_i) = 0
        times = np.array([f[0] for f in flows])
        amounts = np.array([f[1] for f in flows])

        rate = _newton_raphson_xirr(times, amounts)
        if rate is None:
            return None

        return Decimal(str(round(rate, 8)))


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _signed_cash_flow(activity_type: str, amount: Decimal) -> Decimal:
    """Return a signed cash flow amount (positive = money in, negative = money out).

    For deposit/withdrawal/transfer_in/transfer_out the direction is unambiguous
    from the type, so we use abs(amount).  For transfer/receive the provider sign
    is the best signal we have, so we pass it through as-is.
    """
    if activity_type in ("deposit", "transfer_in"):
        return abs(amount)
    elif activity_type in ("withdrawal", "transfer_out"):
        return -abs(amount)
    else:
        # transfer, receive — trust the provider sign
        return amount


def _last_day_of_prev_quarter(ref: date) -> date:
    """Return the last day of the quarter before the one containing *ref*."""
    current_q = (ref.month - 1) // 3 + 1
    if current_q == 1:
        return date(ref.year - 1, 12, 31)
    elif current_q == 2:
        return date(ref.year, 3, 31)
    elif current_q == 3:
        return date(ref.year, 6, 30)
    else:  # Q4
        return date(ref.year, 9, 30)


def _last_quarter(ref: date) -> tuple[date, date]:
    """Return (start, end) of the most recent complete calendar quarter."""
    # Quarter that ref falls in: Q1=1, Q2=2, Q3=3, Q4=4
    current_q = (ref.month - 1) // 3 + 1
    # Go back one quarter
    if current_q == 1:
        return date(ref.year - 1, 10, 1), date(ref.year - 1, 12, 31)
    elif current_q == 2:
        return date(ref.year, 1, 1), date(ref.year, 3, 31)
    elif current_q == 3:
        return date(ref.year, 4, 1), date(ref.year, 6, 30)
    else:  # Q4
        return date(ref.year, 7, 1), date(ref.year, 9, 30)


def _subtract_months(d: date, months: int) -> date:
    """Subtract months from a date, clamping to valid day."""
    year = d.year
    month = d.month - months
    while month <= 0:
        month += 12
        year -= 1
    # Clamp day to max days in target month
    import calendar
    max_day = calendar.monthrange(year, month)[1]
    day = min(d.day, max_day)
    return date(year, month, day)


def _date_to_start_of_day(d: date):
    """Convert date to datetime at start of day (UTC)."""
    from datetime import datetime, timezone
    return datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)


def _date_to_end_of_day(d: date):
    """Convert date to datetime at end of day (UTC)."""
    from datetime import datetime, time, timezone
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def _newton_raphson_xirr(
    times: np.ndarray,
    amounts: np.ndarray,
    guess: float = 0.1,
    max_iter: int = 100,
    tol: float = 1e-8,
) -> float | None:
    """Solve XIRR via Newton-Raphson.

    Finds r such that: sum(amounts[i] / (1+r)^times[i]) = 0
    """
    rate = guess

    for _ in range(max_iter):
        # f(r) = sum(amounts / (1+r)^t)
        denom = (1 + rate) ** times
        if np.any(denom == 0):
            return None

        npv = np.sum(amounts / denom)

        # f'(r) = sum(-t * amounts / (1+r)^(t+1))
        d_npv = np.sum(-times * amounts / ((1 + rate) ** (times + 1)))

        if abs(d_npv) < 1e-14:
            return None

        new_rate = rate - npv / d_npv

        # Guard against divergence
        if new_rate <= -1:
            new_rate = -0.99

        if abs(new_rate - rate) < tol:
            return new_rate

        rate = new_rate

    # Did not converge
    logger.debug("XIRR Newton-Raphson did not converge after %d iterations", max_iter)
    return None
