"""Unit tests for the portfolio returns service."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from models import Account, AccountSnapshot, DailyHoldingValue, SyncSession
from models.activity import Activity
from services.portfolio_returns_service import PortfolioReturnsService
from tests.fixtures import get_or_create_security


# ---------------------------------------------------------------------------
# Helpers to set up DB fixtures
# ---------------------------------------------------------------------------
def _create_account(db: Session, name: str = "Test Account", **kwargs) -> Account:
    acc = Account(
        provider_name=kwargs.get("provider_name", "SnapTrade"),
        external_id=kwargs.get("external_id", f"ext_{name}"),
        name=name,
        is_active=kwargs.get("is_active", True),
        include_in_allocation=kwargs.get("include_in_allocation", True),
    )
    db.add(acc)
    db.flush()
    return acc


def _create_sync_session(
    db: Session,
    ts: datetime | None = None,
) -> SyncSession:
    sync_session = SyncSession(
        timestamp=ts or datetime.now(timezone.utc),
        is_complete=True,
    )
    db.add(sync_session)
    db.flush()
    return sync_session


def _create_account_snapshot(
    db: Session,
    account: Account,
    sync_session: SyncSession,
    total_value: Decimal = Decimal("0"),
    status: str = "success",
) -> AccountSnapshot:
    acct_snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=sync_session.id,
        status=status,
        total_value=total_value,
    )
    db.add(acct_snap)
    db.flush()
    return acct_snap


def _create_dhv(
    db: Session,
    account: Account,
    account_snapshot: AccountSnapshot,
    valuation_date: date,
    ticker: str,
    market_value: Decimal,
    quantity: Decimal = Decimal("10"),
    close_price: Decimal | None = None,
) -> DailyHoldingValue:
    security = get_or_create_security(db, ticker)
    if close_price is None:
        close_price = market_value / quantity if quantity else Decimal("0")
    dhv = DailyHoldingValue(
        valuation_date=valuation_date,
        account_id=account.id,
        account_snapshot_id=account_snapshot.id,
        security_id=security.id,
        ticker=ticker,
        quantity=quantity,
        close_price=close_price,
        market_value=market_value,
    )
    db.add(dhv)
    db.flush()
    return dhv


def _create_activity(
    db: Session,
    account: Account,
    activity_date: date,
    activity_type: str,
    amount: Decimal,
    **kwargs,
) -> Activity:
    act = Activity(
        account_id=account.id,
        provider_name=kwargs.get("provider_name", "SnapTrade"),
        external_id=kwargs.get("external_id", f"act_{activity_date}_{activity_type}_{amount}"),
        activity_date=datetime.combine(activity_date, time(12, 0), tzinfo=timezone.utc),
        type=activity_type,
        amount=amount,
        description=kwargs.get("description", f"{activity_type} of {amount}"),
    )
    db.add(act)
    db.flush()
    return act


def _populate_daily_values(
    db: Session,
    account: Account,
    account_snapshot: AccountSnapshot,
    start: date,
    end: date,
    ticker: str,
    start_value: Decimal,
    daily_growth: Decimal = Decimal("0"),
) -> None:
    """Create DHVs for every day in [start, end] with linear growth."""
    current = start
    value = start_value
    while current <= end:
        _create_dhv(db, account, account_snapshot, current, ticker, value)
        value += daily_growth
        current += timedelta(days=1)
    db.flush()


# ---------------------------------------------------------------------------
# TestPeriodDates
# ---------------------------------------------------------------------------
class TestPeriodDates:
    """Test _get_period_dates maps period strings to correct date ranges."""

    def test_1d(self):
        end = date(2025, 6, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("1D", end)
        assert start == date(2025, 6, 14)
        assert result_end == end

    def test_1m(self):
        end = date(2025, 6, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("1M", end)
        assert start == date(2025, 5, 15)
        assert result_end == end

    def test_3m(self):
        end = date(2025, 6, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("3M", end)
        assert start == date(2025, 3, 15)
        assert result_end == end

    def test_qtd_from_q1(self):
        """QTD in Q1 → starts from Dec 31 of previous year."""
        end = date(2025, 2, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("QTD", end)
        assert start == date(2024, 12, 31)
        assert result_end == end

    def test_qtd_from_q2(self):
        """QTD in Q2 → starts from Mar 31."""
        end = date(2025, 6, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("QTD", end)
        assert start == date(2025, 3, 31)
        assert result_end == end

    def test_qtd_from_q3(self):
        """QTD in Q3 → starts from Jun 30."""
        end = date(2025, 8, 10)
        start, result_end = PortfolioReturnsService._get_period_dates("QTD", end)
        assert start == date(2025, 6, 30)
        assert result_end == end

    def test_qtd_from_q4(self):
        """QTD in Q4 → starts from Sep 30."""
        end = date(2025, 11, 20)
        start, result_end = PortfolioReturnsService._get_period_dates("QTD", end)
        assert start == date(2025, 9, 30)
        assert result_end == end

    def test_ytd(self):
        end = date(2025, 6, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("YTD", end)
        assert start == date(2024, 12, 31)
        assert result_end == end

    def test_1y(self):
        end = date(2025, 6, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("1Y", end)
        assert start == date(2024, 6, 15)
        assert result_end == end

    def test_3y(self):
        end = date(2025, 6, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("3Y", end)
        assert start == date(2022, 6, 15)
        assert result_end == end

    def test_lq_from_q2(self):
        """LQ in Q2 → Q1 of same year (Jan 1 - Mar 31)."""
        end = date(2025, 6, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("LQ", end)
        assert start == date(2025, 1, 1)
        assert result_end == date(2025, 3, 31)

    def test_lq_from_q1(self):
        """LQ in Q1 → Q4 of previous year."""
        end = date(2025, 2, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("LQ", end)
        assert start == date(2024, 10, 1)
        assert result_end == date(2024, 12, 31)

    def test_lq_from_q3(self):
        """LQ in Q3 → Q2 of same year."""
        end = date(2025, 8, 10)
        start, result_end = PortfolioReturnsService._get_period_dates("LQ", end)
        assert start == date(2025, 4, 1)
        assert result_end == date(2025, 6, 30)

    def test_lq_from_q4(self):
        """LQ in Q4 → Q3 of same year."""
        end = date(2025, 11, 20)
        start, result_end = PortfolioReturnsService._get_period_dates("LQ", end)
        assert start == date(2025, 7, 1)
        assert result_end == date(2025, 9, 30)

    def test_ly(self):
        """LY → previous full calendar year."""
        end = date(2025, 6, 15)
        start, result_end = PortfolioReturnsService._get_period_dates("LY", end)
        assert start == date(2024, 1, 1)
        assert result_end == date(2024, 12, 31)

    def test_ly_january(self):
        """LY from early January still gives previous year."""
        end = date(2025, 1, 2)
        start, result_end = PortfolioReturnsService._get_period_dates("LY", end)
        assert start == date(2024, 1, 1)
        assert result_end == date(2024, 12, 31)

    def test_1m_end_of_month_clamp(self):
        """March 31 minus 1 month should be Feb 28 (or 29 in leap year)."""
        end = date(2025, 3, 31)
        start, _ = PortfolioReturnsService._get_period_dates("1M", end)
        assert start == date(2025, 2, 28)

    def test_unknown_period_raises(self):
        with pytest.raises(ValueError, match="Unknown period"):
            PortfolioReturnsService._get_period_dates("5Y", date(2025, 6, 15))


# ---------------------------------------------------------------------------
# TestGetDailyValues
# ---------------------------------------------------------------------------
class TestGetDailyValues:
    """Test _get_daily_values aggregation from DHV table."""

    def test_sums_across_holdings(self, db: Session):
        """Multiple holdings on the same day should sum."""
        account = _create_account(db, "Acct1")
        ss = _create_sync_session(db)
        snap = _create_account_snapshot(db, account, ss)
        d = date(2025, 6, 10)
        _create_dhv(db, account, snap, d, "AAPL", Decimal("1000"))
        _create_dhv(db, account, snap, d, "GOOGL", Decimal("2000"))
        db.flush()

        result = PortfolioReturnsService._get_daily_values(
            db, d, d,
        )
        assert result[d] == Decimal("3000")

    def test_sums_across_accounts(self, db: Session):
        """Multiple accounts on the same day should sum for portfolio-level."""
        acc1 = _create_account(db, "Acct1")
        acc2 = _create_account(db, "Acct2")
        ss = _create_sync_session(db)
        snap1 = _create_account_snapshot(db, acc1, ss)
        snap2 = _create_account_snapshot(db, acc2, ss)
        d = date(2025, 6, 10)
        _create_dhv(db, acc1, snap1, d, "AAPL", Decimal("1000"))
        _create_dhv(db, acc2, snap2, d, "GOOGL", Decimal("500"))
        db.flush()

        result = PortfolioReturnsService._get_daily_values(db, d, d)
        assert result[d] == Decimal("1500")

    def test_filters_by_account_ids(self, db: Session):
        """When account_ids specified, only include those accounts."""
        acc1 = _create_account(db, "Acct1")
        acc2 = _create_account(db, "Acct2")
        ss = _create_sync_session(db)
        snap1 = _create_account_snapshot(db, acc1, ss)
        snap2 = _create_account_snapshot(db, acc2, ss)
        d = date(2025, 6, 10)
        _create_dhv(db, acc1, snap1, d, "AAPL", Decimal("1000"))
        _create_dhv(db, acc2, snap2, d, "GOOGL", Decimal("500"))
        db.flush()

        result = PortfolioReturnsService._get_daily_values(
            db, d, d, account_ids=[acc1.id],
        )
        assert result[d] == Decimal("1000")

    def test_multiple_days(self, db: Session):
        """Should return values grouped by date."""
        acc = _create_account(db, "Acct1")
        ss = _create_sync_session(db)
        snap = _create_account_snapshot(db, acc, ss)
        d1 = date(2025, 6, 10)
        d2 = date(2025, 6, 11)
        _create_dhv(db, acc, snap, d1, "AAPL", Decimal("1000"))
        _create_dhv(db, acc, snap, d2, "AAPL", Decimal("1050"))
        db.flush()

        result = PortfolioReturnsService._get_daily_values(db, d1, d2)
        assert result[d1] == Decimal("1000")
        assert result[d2] == Decimal("1050")

    def test_empty_range(self, db: Session):
        """No data in range returns empty dict."""
        result = PortfolioReturnsService._get_daily_values(
            db, date(2025, 1, 1), date(2025, 1, 2),
        )
        assert result == {}


# ---------------------------------------------------------------------------
# TestGetExternalCashFlows
# ---------------------------------------------------------------------------
class TestGetExternalCashFlows:
    """Test _get_external_cash_flows queries and sign handling."""

    def test_deposit_positive_amount(self, db: Session):
        """Deposit with positive amount → positive cash flow (money in)."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "deposit", Decimal("5000"))
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        assert d in result
        assert len(result[d]) == 1
        assert result[d][0] == Decimal("5000")

    def test_deposit_negative_amount_uses_abs(self, db: Session):
        """Some providers store deposit amount as negative — we use abs()."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "deposit", Decimal("-5000"))
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        assert result[d][0] == Decimal("5000")

    def test_withdrawal_positive_amount(self, db: Session):
        """Withdrawal with positive amount → negative cash flow (money out)."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "withdrawal", Decimal("3000"))
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        assert result[d][0] == Decimal("-3000")

    def test_withdrawal_negative_amount_uses_abs(self, db: Session):
        """Withdrawal with negative amount → still negative cash flow."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "withdrawal", Decimal("-3000"))
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        assert result[d][0] == Decimal("-3000")

    def test_ignores_non_cash_flow_types(self, db: Session):
        """buy/sell/dividend activities are not external cash flows."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "buy", Decimal("1000"))
        _create_activity(db, acc, d, "sell", Decimal("500"))
        _create_activity(db, acc, d, "dividend", Decimal("50"))
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        assert result == {}

    def test_multiple_flows_same_day(self, db: Session):
        """Multiple cash flows on the same day are kept as separate entries."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(
            db, acc, d, "deposit", Decimal("5000"),
            external_id="dep1",
        )
        _create_activity(
            db, acc, d, "withdrawal", Decimal("2000"),
            external_id="wdraw1",
        )
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        flows = sorted(result[d], reverse=True)
        assert flows == [Decimal("5000"), Decimal("-2000")]

    def test_filters_by_account_ids(self, db: Session):
        """When account_ids specified, only include those accounts."""
        acc1 = _create_account(db, "Acct1")
        acc2 = _create_account(db, "Acct2")
        d = date(2025, 6, 10)
        _create_activity(db, acc1, d, "deposit", Decimal("5000"),
                         external_id="dep_acc1")
        _create_activity(db, acc2, d, "deposit", Decimal("3000"),
                         external_id="dep_acc2")
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(
            db, d, d, account_ids=[acc1.id],
        )
        assert len(result[d]) == 1
        assert result[d][0] == Decimal("5000")

    def test_null_amount_skipped(self, db: Session):
        """Activities with null amount should be skipped."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "deposit", None)
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        assert result == {}

    def test_transfer_positive_amount(self, db: Session):
        """Transfer with positive amount → positive (inflow, sign as-is)."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "transfer", Decimal("7000"))
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        assert result[d][0] == Decimal("7000")

    def test_transfer_negative_amount(self, db: Session):
        """Transfer with negative amount → negative (outflow, sign as-is)."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "transfer", Decimal("-4000"))
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        assert result[d][0] == Decimal("-4000")

    def test_receive_positive_amount(self, db: Session):
        """Receive with positive amount → positive (inflow, sign as-is)."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "receive", Decimal("2500"))
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        assert result[d][0] == Decimal("2500")

    def test_receive_negative_amount(self, db: Session):
        """Receive with negative amount → negative (sign as-is)."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "receive", Decimal("-1000"))
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        assert result[d][0] == Decimal("-1000")

    def test_mixed_types_same_day(self, db: Session):
        """Deposit, withdrawal, and transfer on the same day."""
        acc = _create_account(db, "Acct1")
        d = date(2025, 6, 10)
        _create_activity(db, acc, d, "deposit", Decimal("5000"),
                         external_id="dep1")
        _create_activity(db, acc, d, "withdrawal", Decimal("2000"),
                         external_id="wdraw1")
        _create_activity(db, acc, d, "transfer", Decimal("-3000"),
                         external_id="xfer1")
        db.flush()

        result = PortfolioReturnsService._get_external_cash_flows(db, d, d)
        flows = sorted(result[d], reverse=True)
        assert flows == [Decimal("5000"), Decimal("-2000"), Decimal("-3000")]


# ---------------------------------------------------------------------------
# TestXIRR
# ---------------------------------------------------------------------------
class TestXIRR:
    """Test _compute_xirr (money-weighted return / IRR)."""

    def test_simple_growth_no_flows(self):
        """Without cash flows, IRR ≈ TWR (cumulative)."""
        # 1000 → 1100 over ~1 year → 10% cumulative
        start_val = Decimal("1000")
        end_val = Decimal("1100")
        start = date(2024, 6, 15)
        end = date(2025, 6, 15)
        irr = PortfolioReturnsService._compute_xirr(
            start_val, end_val, {}, start, end,
        )
        assert irr is not None
        # ~10% cumulative
        assert abs(irr - Decimal("0.1")) < Decimal("0.01")

    def test_deposit_affects_irr(self):
        """IRR should differ from TWR when deposits are made.

        Depositing money just before a gain amplifies the money-weighted return.
        """
        start_val = Decimal("1000")
        end_val = Decimal("2200")  # 1000 + 1000 deposit + 200 gain
        start = date(2025, 1, 1)
        end = date(2025, 7, 1)
        # Large deposit halfway through
        cash_flows = {
            date(2025, 4, 1): [Decimal("1000")],
        }
        irr = PortfolioReturnsService._compute_xirr(
            start_val, end_val, cash_flows, start, end,
        )
        assert irr is not None
        # Should be positive — money grew
        assert irr > Decimal("0")

    def test_no_cash_flows_short_period(self):
        """IRR over a short period with no flows ≈ cumulative return."""
        start_val = Decimal("10000")
        end_val = Decimal("10100")
        start = date(2025, 6, 1)
        end = date(2025, 6, 30)
        irr = PortfolioReturnsService._compute_xirr(
            start_val, end_val, {}, start, end,
        )
        assert irr is not None
        # ~1% cumulative (not annualized)
        assert abs(irr - Decimal("0.01")) < Decimal("0.001")

    def test_zero_start_value(self):
        """Zero start value with a deposit → should still compute."""
        start_val = Decimal("0")
        end_val = Decimal("1100")
        start = date(2025, 1, 1)
        end = date(2025, 7, 1)
        cash_flows = {
            date(2025, 1, 1): [Decimal("1000")],
        }
        irr = PortfolioReturnsService._compute_xirr(
            start_val, end_val, cash_flows, start, end,
        )
        # May or may not converge — just shouldn't crash
        # If it converges, it should be positive
        if irr is not None:
            assert irr > Decimal("0")

    def test_zero_start_no_flows_returns_none(self):
        """Zero start value with no cash flows → None."""
        irr = PortfolioReturnsService._compute_xirr(
            Decimal("0"), Decimal("1000"), {}, date(2025, 1, 1), date(2025, 7, 1),
        )
        assert irr is None

    def test_withdrawal(self):
        """XIRR with a withdrawal mid-period."""
        start_val = Decimal("10000")
        end_val = Decimal("5500")  # withdrew 5000, gained 500
        start = date(2025, 1, 1)
        end = date(2025, 7, 1)
        cash_flows = {
            date(2025, 4, 1): [Decimal("-5000")],
        }
        irr = PortfolioReturnsService._compute_xirr(
            start_val, end_val, cash_flows, start, end,
        )
        assert irr is not None
        assert irr > Decimal("0")


# ---------------------------------------------------------------------------
# TestPortfolioReturns — full integration with DB
# ---------------------------------------------------------------------------
class TestPortfolioReturns:
    """Test get_portfolio_returns end-to-end with DB fixtures."""

    def test_simple_portfolio_return(self, db: Session):
        """Compute returns for a simple portfolio with daily values."""
        acc = _create_account(db, "Main")
        ss = _create_sync_session(db)
        snap = _create_account_snapshot(db, acc, ss)

        # Create 35 days of daily values (enough for 1M period)
        today = date.today()
        yesterday = today - timedelta(days=1)
        start = yesterday - timedelta(days=34)

        # Start at 10000, grow to ~10500 (about 5%)
        value = Decimal("10000")
        growth_per_day = Decimal("500") / Decimal("34")
        current = start
        while current <= yesterday:
            _create_dhv(db, acc, snap, current, "SPY", value)
            value += growth_per_day
            current += timedelta(days=1)
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_portfolio_returns(db, periods=["1M"])

        assert result.scope_id == "portfolio"
        assert result.scope_name == "Portfolio"
        assert len(result.periods) == 1

        ret = result.periods[0]
        assert ret.period == "1M"
        assert ret.has_sufficient_data is True
        assert ret.irr is not None
        assert ret.irr > Decimal("0")

    def test_insufficient_data(self, db: Session):
        """If no data exists for a period, has_sufficient_data should be False."""
        service = PortfolioReturnsService()
        result = service.get_portfolio_returns(db, periods=["1Y"])

        assert len(result.periods) == 1
        ret = result.periods[0]
        assert ret.has_sufficient_data is False
        assert ret.irr is None

    def test_multiple_periods(self, db: Session):
        """Request multiple periods at once."""
        acc = _create_account(db, "Main")
        ss = _create_sync_session(db)
        snap = _create_account_snapshot(db, acc, ss)

        # Create 400 days of data (enough for 1Y)
        today = date.today()
        yesterday = today - timedelta(days=1)
        start = yesterday - timedelta(days=399)

        _populate_daily_values(
            db, acc, snap, start, yesterday, "SPY",
            start_value=Decimal("10000"), daily_growth=Decimal("5"),
        )
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_portfolio_returns(db, periods=["1D", "1M", "1Y"])

        assert len(result.periods) == 3
        period_map = {r.period: r for r in result.periods}
        for period in ["1D", "1M", "1Y"]:
            assert period in period_map
            assert period_map[period].has_sufficient_data is True
            assert period_map[period].irr is not None

    def test_with_cash_flows(self, db: Session):
        """Returns should account for deposits/withdrawals."""
        acc = _create_account(db, "Main")
        ss = _create_sync_session(db)
        snap = _create_account_snapshot(db, acc, ss)

        today = date.today()
        yesterday = today - timedelta(days=1)
        # Get the actual 1M period start so we place data there
        period_start, period_end = PortfolioReturnsService._get_period_dates(
            "1M", yesterday,
        )

        # Place data at the period boundaries and a few days in between
        deposit_date = period_start + timedelta(days=10)
        values = [
            (period_start, Decimal("10000")),
            (deposit_date - timedelta(days=1), Decimal("10200")),
            (deposit_date, Decimal("15500")),  # deposit 5000 + growth
            (deposit_date + timedelta(days=1), Decimal("15700")),
            (period_end, Decimal("16000")),
        ]
        for d, v in values:
            _create_dhv(db, acc, snap, d, "SPY", v)

        _create_activity(db, acc, deposit_date, "deposit", Decimal("5000"))
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_portfolio_returns(db, periods=["1M"])

        ret = result.periods[0]
        assert ret.has_sufficient_data is True
        assert ret.irr is not None

    def test_excludes_inactive_accounts(self, db: Session):
        """Portfolio returns should not include inactive accounts."""
        acc_active = _create_account(db, "Active")
        acc_inactive = _create_account(db, "Inactive", is_active=False)
        ss = _create_sync_session(db)
        snap_active = _create_account_snapshot(db, acc_active, ss)
        snap_inactive = _create_account_snapshot(db, acc_inactive, ss)

        today = date.today()
        yesterday = today - timedelta(days=1)
        period_start, period_end = PortfolioReturnsService._get_period_dates(
            "1M", yesterday,
        )

        # Active account: 10000 → 11000 (10% gain)
        _create_dhv(db, acc_active, snap_active, period_start, "SPY", Decimal("10000"))
        _create_dhv(db, acc_active, snap_active, period_end, "SPY", Decimal("11000"))
        # Inactive account: 5000 → 4000 (20% loss) — should be excluded
        _create_dhv(db, acc_inactive, snap_inactive, period_start, "BND", Decimal("5000"))
        _create_dhv(db, acc_inactive, snap_inactive, period_end, "BND", Decimal("4000"))
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_portfolio_returns(db, periods=["1M"])
        ret = result.periods[0]

        assert ret.has_sufficient_data is True
        # Should reflect only active account: 10000 → 11000 = +10%
        assert ret.start_value == Decimal("10000")
        assert ret.end_value == Decimal("11000")

    def test_excludes_non_allocation_accounts(self, db: Session):
        """Portfolio returns should not include accounts with include_in_allocation=False."""
        acc_included = _create_account(db, "Included")
        acc_excluded = _create_account(
            db, "Excluded", include_in_allocation=False,
        )
        ss = _create_sync_session(db)
        snap_inc = _create_account_snapshot(db, acc_included, ss)
        snap_exc = _create_account_snapshot(db, acc_excluded, ss)

        today = date.today()
        yesterday = today - timedelta(days=1)
        period_start, period_end = PortfolioReturnsService._get_period_dates(
            "1M", yesterday,
        )

        _create_dhv(db, acc_included, snap_inc, period_start, "SPY", Decimal("10000"))
        _create_dhv(db, acc_included, snap_inc, period_end, "SPY", Decimal("10500"))
        # Excluded account — should not contribute to portfolio values
        _create_dhv(db, acc_excluded, snap_exc, period_start, "COIN", Decimal("20000"))
        _create_dhv(db, acc_excluded, snap_exc, period_end, "COIN", Decimal("10000"))
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_portfolio_returns(db, periods=["1M"])
        ret = result.periods[0]

        assert ret.has_sufficient_data is True
        assert ret.start_value == Decimal("10000")
        assert ret.end_value == Decimal("10500")

    def test_account_returns_ignores_allocation_flag(self, db: Session):
        """get_account_returns works even for excluded accounts."""
        acc = _create_account(db, "Excluded", include_in_allocation=False)
        ss = _create_sync_session(db)
        snap = _create_account_snapshot(db, acc, ss)

        today = date.today()
        yesterday = today - timedelta(days=1)
        period_start, period_end = PortfolioReturnsService._get_period_dates(
            "1M", yesterday,
        )

        _create_dhv(db, acc, snap, period_start, "BTC", Decimal("5000"))
        _create_dhv(db, acc, snap, period_end, "BTC", Decimal("6000"))
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_account_returns(db, acc.id, periods=["1M"])
        ret = result.periods[0]

        assert ret.has_sufficient_data is True
        assert ret.irr is not None
        assert ret.irr > Decimal("0")


# ---------------------------------------------------------------------------
# TestAccountReturns
# ---------------------------------------------------------------------------
class TestAccountReturns:
    """Test get_account_returns for a single account."""

    def test_single_account(self, db: Session):
        """Compute returns for one specific account."""
        acc1 = _create_account(db, "Brokerage")
        acc2 = _create_account(db, "Retirement")
        ss = _create_sync_session(db)
        snap1 = _create_account_snapshot(db, acc1, ss)
        snap2 = _create_account_snapshot(db, acc2, ss)

        today = date.today()
        yesterday = today - timedelta(days=1)
        period_start, period_end = PortfolioReturnsService._get_period_dates(
            "1M", yesterday,
        )

        # acc1: 1000 → 1100 (10% gain)
        _populate_daily_values(
            db, acc1, snap1, period_start, period_end, "AAPL",
            start_value=Decimal("1000"),
            daily_growth=Decimal("100") / Decimal(str((period_end - period_start).days)),
        )
        # acc2: 2000 → 1800 (10% loss)
        _populate_daily_values(
            db, acc2, snap2, period_start, period_end, "BONDS",
            start_value=Decimal("2000"),
            daily_growth=Decimal("-200") / Decimal(str((period_end - period_start).days)),
        )
        db.flush()

        service = PortfolioReturnsService()

        # Check acc1 returns
        result1 = service.get_account_returns(db, acc1.id, periods=["1M"])
        assert result1.scope_id == acc1.id
        assert result1.scope_name == "Brokerage"
        ret1 = result1.periods[0]
        assert ret1.irr is not None
        assert ret1.irr > Decimal("0")

        # Check acc2 returns
        result2 = service.get_account_returns(db, acc2.id, periods=["1M"])
        ret2 = result2.periods[0]
        assert ret2.irr is not None
        assert ret2.irr < Decimal("0")


# ---------------------------------------------------------------------------
# TestAllAccountReturns
# ---------------------------------------------------------------------------
class TestAllAccountReturns:
    """Test get_all_account_returns for all accounts."""

    def test_defaults_to_active_only(self, db: Session):
        """By default, only active accounts are included."""
        acc1 = _create_account(db, "Account A")
        acc2 = _create_account(db, "Account B")
        acc3 = _create_account(db, "Inactive", is_active=False)
        db.flush()

        service = PortfolioReturnsService()
        results = service.get_all_account_returns(db, periods=["1M"])

        scope_ids = {r.scope_id for r in results}
        assert acc1.id in scope_ids
        assert acc2.id in scope_ids
        assert acc3.id not in scope_ids

    def test_include_inactive(self, db: Session):
        """With include_inactive=True, inactive accounts appear too."""
        acc1 = _create_account(db, "Active")
        acc2 = _create_account(db, "Inactive", is_active=False)
        db.flush()

        service = PortfolioReturnsService()
        results = service.get_all_account_returns(
            db, periods=["1M"], include_inactive=True,
        )

        scope_ids = {r.scope_id for r in results}
        assert acc1.id in scope_ids
        assert acc2.id in scope_ids

    def test_empty_accounts(self, db: Session):
        """Accounts with no DHV data still appear with insufficient data."""
        _create_account(db, "Empty Account")
        db.flush()

        service = PortfolioReturnsService()
        results = service.get_all_account_returns(db, periods=["1M"])

        assert len(results) >= 1
        for r in results:
            for p in r.periods:
                assert p.has_sufficient_data is False


# ---------------------------------------------------------------------------
# TestGetReturns — unified entry point
# ---------------------------------------------------------------------------
class TestGetReturns:
    """Test the get_returns unified entry point."""

    def test_scope_all(self, db: Session):
        """scope='all' returns portfolio + all accounts."""
        acc = _create_account(db, "Main")
        ss = _create_sync_session(db)
        snap = _create_account_snapshot(db, acc, ss)

        today = date.today()
        yesterday = today - timedelta(days=1)
        start = yesterday - timedelta(days=5)

        _populate_daily_values(
            db, acc, snap, start, yesterday, "SPY",
            start_value=Decimal("10000"), daily_growth=Decimal("10"),
        )
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_returns(db, scope="all", periods=["1M"])

        assert result.portfolio is not None
        assert result.portfolio.scope_id == "portfolio"
        assert len(result.accounts) >= 1

    def test_scope_portfolio(self, db: Session):
        """scope='portfolio' returns only portfolio-level."""
        service = PortfolioReturnsService()
        result = service.get_returns(db, scope="portfolio", periods=["1M"])

        assert result.portfolio is not None
        assert result.accounts == []

    def test_scope_account_id(self, db: Session):
        """scope=<account_id> returns that account only."""
        acc = _create_account(db, "Target")
        ss = _create_sync_session(db)
        snap = _create_account_snapshot(db, acc, ss)

        today = date.today()
        yesterday = today - timedelta(days=1)
        start = yesterday - timedelta(days=5)

        _populate_daily_values(
            db, acc, snap, start, yesterday, "SPY",
            start_value=Decimal("10000"), daily_growth=Decimal("10"),
        )
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_returns(db, scope=acc.id, periods=["1M"])

        assert result.portfolio is None
        assert len(result.accounts) == 1
        assert result.accounts[0].scope_id == acc.id

    def test_default_periods(self, db: Session):
        """Without periods arg, should use default set."""
        service = PortfolioReturnsService()
        result = service.get_returns(db, scope="portfolio")

        assert result.portfolio is not None
        period_names = {p.period for p in result.portfolio.periods}
        assert "1D" in period_names
        assert "1M" in period_names
        assert "YTD" in period_names


# ---------------------------------------------------------------------------
# TestAnnualization
# ---------------------------------------------------------------------------
class TestReturnsAreCumulative:
    """Test that all returns are cumulative (never annualized)."""

    def test_1y_period_cumulative(self, db: Session):
        """1Y period should return cumulative return."""
        acc = _create_account(db, "Main")
        ss = _create_sync_session(db)
        snap = _create_account_snapshot(db, acc, ss)

        today = date.today()
        yesterday = today - timedelta(days=1)
        start = yesterday - timedelta(days=365)

        # 10% return over 1 year
        _create_dhv(db, acc, snap, start, "SPY", Decimal("10000"))
        _create_dhv(db, acc, snap, yesterday, "SPY", Decimal("11000"))
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_portfolio_returns(db, periods=["1Y"])
        ret = result.periods[0]
        assert ret.irr is not None
        assert abs(ret.irr - Decimal("0.1")) < Decimal("0.01")

    def test_3y_period_cumulative(self, db: Session):
        """3Y period should return cumulative return, not annualized."""
        acc = _create_account(db, "Main")
        ss = _create_sync_session(db)
        snap = _create_account_snapshot(db, acc, ss)

        today = date.today()
        yesterday = today - timedelta(days=1)
        period_start, period_end = PortfolioReturnsService._get_period_dates(
            "3Y", yesterday,
        )

        # 33.1% cumulative return over 3 years
        _create_dhv(db, acc, snap, period_start, "SPY", Decimal("10000"))
        _create_dhv(db, acc, snap, period_end, "SPY", Decimal("13310"))
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_portfolio_returns(db, periods=["3Y"])
        ret = result.periods[0]
        assert ret.irr is not None
        # Cumulative ~33.1% (not annualized to ~10%)
        assert abs(ret.irr - Decimal("0.331")) < Decimal("0.01")


# ---------------------------------------------------------------------------
# TestAccountsEmptied
# ---------------------------------------------------------------------------
class TestAccountsEmptied:
    """Test _accounts_emptied detects liquidated accounts."""

    def test_empty_account_detected(self, db: Session):
        """Account with total_value=0 in latest snapshot is considered emptied."""
        acc = _create_account(db, "Liquidated")
        ss = _create_sync_session(db, datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc))
        _create_account_snapshot(db, acc, ss, total_value=Decimal("0"))
        db.flush()

        service = PortfolioReturnsService()
        assert service._accounts_emptied(db, [acc.id], date(2026, 2, 14)) is True

    def test_non_empty_account_not_detected(self, db: Session):
        """Account with total_value > 0 is not considered emptied."""
        acc = _create_account(db, "Active")
        ss = _create_sync_session(db, datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc))
        _create_account_snapshot(db, acc, ss, total_value=Decimal("50000"))
        db.flush()

        service = PortfolioReturnsService()
        assert service._accounts_emptied(db, [acc.id], date(2026, 2, 14)) is False

    def test_no_snapshot_returns_false(self, db: Session):
        """Account with no snapshots cannot be confirmed emptied."""
        acc = _create_account(db, "NoSnaps")
        db.flush()

        service = PortfolioReturnsService()
        assert service._accounts_emptied(db, [acc.id], date(2026, 2, 14)) is False

    def test_uses_latest_snapshot_only(self, db: Session):
        """Earlier non-zero snapshot should be ignored if latest is zero."""
        acc = _create_account(db, "WasActive")
        ss1 = _create_sync_session(db, datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))
        _create_account_snapshot(db, acc, ss1, total_value=Decimal("100000"))
        ss2 = _create_sync_session(db, datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc))
        _create_account_snapshot(db, acc, ss2, total_value=Decimal("0"))
        db.flush()

        service = PortfolioReturnsService()
        assert service._accounts_emptied(db, [acc.id], date(2026, 2, 14)) is True

    def test_ignores_snapshots_after_as_of(self, db: Session):
        """Snapshots after the as_of date should not be considered."""
        acc = _create_account(db, "FutureEmpty")
        ss1 = _create_sync_session(db, datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))
        _create_account_snapshot(db, acc, ss1, total_value=Decimal("50000"))
        # This emptied snapshot is AFTER as_of
        ss2 = _create_sync_session(db, datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc))
        _create_account_snapshot(db, acc, ss2, total_value=Decimal("0"))
        db.flush()

        service = PortfolioReturnsService()
        assert service._accounts_emptied(db, [acc.id], date(2026, 2, 14)) is False

    def test_multiple_accounts_all_must_be_empty(self, db: Session):
        """Returns True only if ALL accounts are emptied."""
        acc1 = _create_account(db, "Empty1", external_id="e1")
        acc2 = _create_account(db, "StillActive", external_id="e2")
        ss = _create_sync_session(db, datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc))
        _create_account_snapshot(db, acc1, ss, total_value=Decimal("0"))
        _create_account_snapshot(db, acc2, ss, total_value=Decimal("10000"))
        db.flush()

        service = PortfolioReturnsService()
        assert service._accounts_emptied(db, [acc1.id, acc2.id], date(2026, 2, 14)) is False

    def test_ignores_failed_snapshots(self, db: Session):
        """Failed snapshots should not be used to determine emptied status."""
        acc = _create_account(db, "FailedSync")
        ss1 = _create_sync_session(db, datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))
        _create_account_snapshot(db, acc, ss1, total_value=Decimal("50000"))
        ss2 = _create_sync_session(db, datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc))
        _create_account_snapshot(db, acc, ss2, total_value=Decimal("0"), status="failed")
        db.flush()

        service = PortfolioReturnsService()
        # Should fall back to the earlier successful snapshot which has value
        assert service._accounts_emptied(db, [acc.id], date(2026, 2, 14)) is False


# ---------------------------------------------------------------------------
# TestLiquidatedAccountReturns
# ---------------------------------------------------------------------------
class TestLiquidatedAccountReturns:
    """Test that liquidated accounts infer $0 end value and compute returns."""

    def test_liquidated_account_shows_negative_return(self, db: Session):
        """An account emptied mid-period should show a negative return, not '--'."""
        acc = _create_account(db, "Liquidated")

        today = date.today()
        yesterday = today - timedelta(days=1)
        period_start, period_end = PortfolioReturnsService._get_period_dates(
            "1M", yesterday,
        )

        # Snapshot with holdings at start
        ss1 = _create_sync_session(db, datetime.combine(period_start, time(12, 0), tzinfo=timezone.utc))
        snap1 = _create_account_snapshot(db, acc, ss1, total_value=Decimal("100000"))
        _create_dhv(db, acc, snap1, period_start, "VOO", Decimal("100000"))

        # Mid-period: still has value
        mid = period_start + timedelta(days=10)
        _create_dhv(db, acc, snap1, mid, "VOO", Decimal("102000"))

        # Final snapshot: emptied (no DHV rows, total_value=0)
        ss2 = _create_sync_session(db, datetime.combine(period_end - timedelta(days=1), time(12, 0), tzinfo=timezone.utc))
        _create_account_snapshot(db, acc, ss2, total_value=Decimal("0"))
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_account_returns(db, acc.id, periods=["1M"])
        ret = result.periods[0]

        assert ret.has_sufficient_data is True
        assert ret.end_value == Decimal("0")
        # IRR of exactly -100% is a mathematical singularity (division by zero
        # at r=-1), so Newton-Raphson cannot converge. This is expected.
        # The key assertion is that has_sufficient_data=True and end_value=0,
        # so the frontend can display "-100%" directly from the values.

    def test_no_inference_when_account_still_has_value(self, db: Session):
        """Should not infer $0 when account still has holdings."""
        acc = _create_account(db, "StillActive")

        today = date.today()
        yesterday = today - timedelta(days=1)
        period_start, period_end = PortfolioReturnsService._get_period_dates(
            "1M", yesterday,
        )

        # Snapshot with value
        ss = _create_sync_session(db, datetime.combine(period_start, time(12, 0), tzinfo=timezone.utc))
        snap = _create_account_snapshot(db, acc, ss, total_value=Decimal("100000"))
        _create_dhv(db, acc, snap, period_start, "VOO", Decimal("100000"))
        # No end-date DHV, but snapshot says account still has value
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_account_returns(db, acc.id, periods=["1M"])
        ret = result.periods[0]

        # Should NOT infer $0 — insufficient data
        assert ret.has_sufficient_data is False

    def test_no_inference_when_no_start_data(self, db: Session):
        """Should not infer anything when start date has no data."""
        acc = _create_account(db, "NewAccount")

        today = date.today()
        yesterday = today - timedelta(days=1)
        period_start, period_end = PortfolioReturnsService._get_period_dates(
            "1M", yesterday,
        )

        # Only a zero snapshot, no DHV at start
        ss = _create_sync_session(db, datetime.combine(period_end, time(12, 0), tzinfo=timezone.utc))
        _create_account_snapshot(db, acc, ss, total_value=Decimal("0"))
        db.flush()

        service = PortfolioReturnsService()
        result = service.get_account_returns(db, acc.id, periods=["1M"])
        ret = result.periods[0]

        assert ret.has_sufficient_data is False
