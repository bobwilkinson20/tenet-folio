"""Portfolio valuation service — computes and stores daily holding values."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Account, AccountSnapshot, DailyHoldingValue, Holding, SyncSession
from models.asset_class import AssetClass
from models.security import Security
from services.market_data_service import MarketDataService
from services.security_service import SecurityService
from utils.ticker import ZERO_BALANCE_TICKER

logger = logging.getLogger(__name__)

# Tickers treated as cash equivalents (always priced at $1.00).
CASH_TICKERS = frozenset({
    "USD", "CASH", "CAD",
    # Common money market / sweep funds
    "SPAXX", "FDRXX", "SWVXX", "VMFXX", "FZFXX",
})


@dataclass
class HoldingSummary:
    """Lightweight holding data extracted from a snapshot."""

    ticker: str
    security_id: str
    quantity: Decimal
    snapshot_price: Decimal


@dataclass
class SnapshotWindow:
    """A snapshot's holdings and the date it takes effect."""

    effective_date: date
    account_snapshot_id: str
    holdings: list[HoldingSummary]


@dataclass
class ValuationResult:
    """Summary of a valuation backfill run."""

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    dates_calculated: int = 0
    holdings_written: int = 0
    symbols_fetched: int = 0
    errors: list[str] = field(default_factory=list)


def is_cash_equivalent(ticker: str, snapshot_price: Decimal) -> bool:
    """Determine if a holding is a cash equivalent.

    Uses explicit ticker matching only. The snapshot_price parameter is
    retained for backward compatibility but is no longer used for heuristic
    detection (the price == $1 check was too fragile).
    """
    if ticker.upper() in CASH_TICKERS:
        return True
    if ticker.startswith("_CASH:"):
        return True
    return False


def build_price_lookup(
    market_data: dict[str, list],
    start_date: date,
    end_date: date,
) -> dict[str, dict[date, Decimal]]:
    """Build a symbol -> date -> price mapping with carry-forward.

    For each calendar day in the range, if no price exists for that day,
    the most recent prior price is used. This handles weekends, holidays,
    and symbols with sparse data.
    """
    lookup: dict[str, dict[date, Decimal]] = {}

    for symbol, prices in market_data.items():
        sorted_prices = sorted(prices, key=lambda p: p.price_date)

        price_map: dict[date, Decimal] = {}
        last_price: Optional[Decimal] = None
        price_idx = 0

        current = start_date
        while current <= end_date:
            while (
                price_idx < len(sorted_prices)
                and sorted_prices[price_idx].price_date <= current
            ):
                last_price = sorted_prices[price_idx].close_price
                price_idx += 1

            if last_price is not None:
                price_map[current] = last_price

            current += timedelta(days=1)

        lookup[symbol] = price_map

    return lookup


class PortfolioValuationService:
    """Computes and stores daily portfolio valuations.

    Uses holdings from sync snapshots combined with market close prices
    to calculate the value of every holding for every calendar day.
    Results are persisted to daily_holding_values for efficient querying.
    """

    @staticmethod
    def create_daily_values_for_holdings(
        db: Session,
        holdings: list[Holding],
        valuation_date: date,
        account_id: str,
    ) -> list[DailyHoldingValue]:
        """Create DailyHoldingValue rows for holdings using their snapshot prices.

        Uses upsert semantics: if a row already exists for the same
        (valuation_date, account_id, security_id) it is updated
        rather than duplicated.

        Args:
            db: Database session
            holdings: Holding records (must already be flushed with IDs)
            valuation_date: The date to record values for
            account_id: The account ID these holdings belong to

        Returns:
            List of created/updated DailyHoldingValue rows
        """
        rows: list[DailyHoldingValue] = []
        for h in holdings:
            existing = (
                db.query(DailyHoldingValue)
                .filter(
                    DailyHoldingValue.valuation_date == valuation_date,
                    DailyHoldingValue.account_id == account_id,
                    DailyHoldingValue.security_id == h.security_id,
                )
                .first()
            )
            if existing:
                existing.ticker = h.ticker
                existing.quantity = h.quantity
                existing.close_price = h.snapshot_price
                existing.market_value = h.snapshot_value
                existing.account_snapshot_id = h.account_snapshot_id
                rows.append(existing)
            else:
                dhv = DailyHoldingValue(
                    valuation_date=valuation_date,
                    account_id=account_id,
                    account_snapshot_id=h.account_snapshot_id,
                    security_id=h.security_id,
                    ticker=h.ticker,
                    quantity=h.quantity,
                    close_price=h.snapshot_price,
                    market_value=h.snapshot_value,
                )
                db.add(dhv)
                rows.append(dhv)
        return rows

    @staticmethod
    def write_zero_balance_sentinel(
        db: Session,
        account_id: str,
        account_snapshot_id: str,
        valuation_date: date,
    ) -> DailyHoldingValue:
        """Write a sentinel DHV row indicating an account has zero holdings.

        Lazy-creates the _ZERO_BALANCE Security if it doesn't exist.
        Uses upsert semantics: updates an existing sentinel row if present.
        Also deletes any stale real DHV rows for the same account+date.

        Args:
            db: Database session
            account_id: The account with zero holdings
            account_snapshot_id: The snapshot confirming zero holdings
            valuation_date: The date to record the sentinel for

        Returns:
            The created/updated DailyHoldingValue sentinel row
        """
        security = SecurityService.ensure_exists(
            db, ZERO_BALANCE_TICKER, name="Zero Balance Sentinel"
        )

        # Delete any stale real (non-sentinel) DHV rows for this account+date
        db.query(DailyHoldingValue).filter(
            DailyHoldingValue.valuation_date == valuation_date,
            DailyHoldingValue.account_id == account_id,
            DailyHoldingValue.security_id != security.id,
        ).delete(synchronize_session="fetch")

        # Upsert the sentinel row
        existing = (
            db.query(DailyHoldingValue)
            .filter(
                DailyHoldingValue.valuation_date == valuation_date,
                DailyHoldingValue.account_id == account_id,
                DailyHoldingValue.security_id == security.id,
            )
            .first()
        )
        if existing:
            existing.account_snapshot_id = account_snapshot_id
            existing.quantity = Decimal("0")
            existing.close_price = Decimal("0")
            existing.market_value = Decimal("0")
            return existing

        dhv = DailyHoldingValue(
            valuation_date=valuation_date,
            account_id=account_id,
            account_snapshot_id=account_snapshot_id,
            security_id=security.id,
            ticker=ZERO_BALANCE_TICKER,
            quantity=Decimal("0"),
            close_price=Decimal("0"),
            market_value=Decimal("0"),
        )
        db.add(dhv)
        return dhv

    @staticmethod
    def delete_zero_balance_sentinel(
        db: Session,
        account_id: str,
        valuation_date: date,
    ) -> None:
        """Delete the sentinel DHV row for an account+date if it exists.

        No-op if the _ZERO_BALANCE Security doesn't exist yet.

        Args:
            db: Database session
            account_id: The account to clean up
            valuation_date: The date to remove the sentinel for
        """
        from models import Security

        security = db.query(Security).filter_by(ticker=ZERO_BALANCE_TICKER).first()
        if security is None:
            return

        db.query(DailyHoldingValue).filter(
            DailyHoldingValue.valuation_date == valuation_date,
            DailyHoldingValue.account_id == account_id,
            DailyHoldingValue.security_id == security.id,
        ).delete(synchronize_session="fetch")

    def __init__(
        self,
        market_data_service: Optional[MarketDataService] = None,
    ):
        self._market_data_service = market_data_service

    @property
    def market_data_service(self) -> MarketDataService:
        if self._market_data_service is None:
            self._market_data_service = MarketDataService()
        return self._market_data_service

    def backfill(self, db: Session) -> ValuationResult:
        """Calculate and store valuations for all missing dates.

        Determines the gap between last stored valuation and yesterday,
        then runs the full algorithm for that range.
        """
        start_date = self._get_start_date(db)
        if start_date is None:
            logger.info("No snapshots found — skipping valuation backfill")
            return ValuationResult()

        end_date = date.today() - timedelta(days=1)
        if start_date > end_date:
            logger.info("Valuations already current through %s", end_date)
            return ValuationResult()

        return self._run_backfill(db, start_date, end_date)

    def full_backfill(self, db: Session, repair: bool = False) -> ValuationResult:
        """Backfill from the earliest snapshot through yesterday.

        Ignores the start_date optimization — forces a full recompute.
        Use this to fill historical gaps in DHV data.

        Args:
            repair: If True, overwrite all fields on existing rows
                    (including account_snapshot_id and quantity).
                    Only the CLI repair tool should use this.
        """
        first_session = (
            db.query(SyncSession)
            .filter(SyncSession.is_complete.is_(True))
            .order_by(SyncSession.timestamp.asc())
            .first()
        )
        if first_session is None:
            logger.info("No completed sync sessions — skipping full backfill")
            return ValuationResult()

        start_date = self._utc_to_local_date(first_session.timestamp)
        end_date = date.today() - timedelta(days=1)
        if start_date > end_date:
            return ValuationResult()

        return self._run_backfill(db, start_date, end_date, repair=repair)

    def diagnose_gaps(self, db: Session) -> list[dict]:
        """Analyze DHV gaps for each active account.

        Returns a list of per-account diagnostics with:
        - account_id, account_name
        - expected_start, expected_end (first snapshot → yesterday)
        - expected_days, actual_days, missing_days
        - missing_dates (list, capped at 100)
        """
        yesterday = date.today() - timedelta(days=1)
        all_accounts = db.query(Account).all()

        # Look up sentinel security once (shared across all accounts)
        sentinel_security = (
            db.query(Security)
            .filter_by(ticker=ZERO_BALANCE_TICKER)
            .first()
        )
        sentinel_id = sentinel_security.id if sentinel_security else None

        results = []
        for account in all_accounts:
            # Find first and last successful snapshot dates for this account
            first_snap = (
                db.query(AccountSnapshot)
                .join(SyncSession)
                .filter(
                    AccountSnapshot.account_id == account.id,
                    AccountSnapshot.status == "success",
                    SyncSession.is_complete.is_(True),
                )
                .order_by(SyncSession.timestamp.asc())
                .first()
            )
            if first_snap is None:
                continue

            expected_start = self._utc_to_local_date(first_snap.sync_session.timestamp)

            # Active accounts should have DHV through yesterday.
            # Inactive accounts should have DHV through their last snapshot.
            if account.is_active:
                expected_end = yesterday
            else:
                last_snap = (
                    db.query(AccountSnapshot)
                    .join(SyncSession)
                    .filter(
                        AccountSnapshot.account_id == account.id,
                        AccountSnapshot.status == "success",
                        SyncSession.is_complete.is_(True),
                    )
                    .order_by(SyncSession.timestamp.desc())
                    .first()
                )
                expected_end = self._utc_to_local_date(last_snap.sync_session.timestamp)

            if expected_start > expected_end:
                continue

            # All dates we expect DHV rows for
            expected_days = (expected_end - expected_start).days + 1

            # Dates that actually have DHV rows
            actual_dates = set(
                row[0]
                for row in db.query(DailyHoldingValue.valuation_date)
                .filter(
                    DailyHoldingValue.account_id == account.id,
                    DailyHoldingValue.valuation_date >= expected_start,
                    DailyHoldingValue.valuation_date <= expected_end,
                )
                .distinct()
                .all()
            )

            # Compute missing dates
            all_expected = set()
            current = expected_start
            while current <= expected_end:
                all_expected.add(current)
                current += timedelta(days=1)

            missing = sorted(all_expected - actual_dates)

            # Detect partial gaps: dates present but with fewer DHV rows
            # than the governing snapshot's holding count.
            partial: list[date] = []
            if actual_dates:
                # DHV row counts per (valuation_date, account_snapshot_id)
                dhv_q = (
                    db.query(
                        DailyHoldingValue.valuation_date,
                        DailyHoldingValue.account_snapshot_id,
                        func.count(DailyHoldingValue.id),
                    )
                    .filter(
                        DailyHoldingValue.account_id == account.id,
                        DailyHoldingValue.valuation_date >= expected_start,
                        DailyHoldingValue.valuation_date <= expected_end,
                    )
                )
                if sentinel_id:
                    dhv_q = dhv_q.filter(
                        DailyHoldingValue.security_id != sentinel_id
                    )
                dhv_counts = {
                    (row[0], row[1]): row[2]
                    for row in dhv_q.group_by(
                        DailyHoldingValue.valuation_date,
                        DailyHoldingValue.account_snapshot_id,
                    ).all()
                }

                # Holding counts per account_snapshot_id (non-sentinel)
                holding_q = (
                    db.query(
                        Holding.account_snapshot_id,
                        func.count(Holding.id),
                    )
                    .join(AccountSnapshot)
                    .filter(AccountSnapshot.account_id == account.id)
                )
                if sentinel_id:
                    holding_q = holding_q.filter(
                        Holding.security_id != sentinel_id
                    )
                holding_counts = {
                    row[0]: row[1]
                    for row in holding_q.group_by(
                        Holding.account_snapshot_id
                    ).all()
                }

                # Compare: for each date+snapshot combo, check if DHV < holdings
                seen_dates: set[date] = set()
                for (val_date, snap_id), dhv_count in dhv_counts.items():
                    expected_count = holding_counts.get(snap_id, 0)
                    if expected_count > 0 and dhv_count < expected_count:
                        seen_dates.add(val_date)
                partial = sorted(seen_dates)

            results.append({
                "account_id": account.id,
                "account_name": account.name,
                "expected_start": expected_start,
                "expected_end": expected_end,
                "expected_days": expected_days,
                "actual_days": len(actual_dates),
                "missing_days": len(missing),
                "missing_dates": [d.isoformat() for d in missing[:100]],
                "partial_days": len(partial),
                "partial_dates": [d.isoformat() for d in partial[:100]],
            })

        return results

    def _run_backfill(
        self, db: Session, start_date: date, end_date: date,
        repair: bool = False,
    ) -> ValuationResult:
        """Core backfill loop: compute and upsert DHV rows for a date range.

        Args:
            repair: If True, overwrite all fields on existing rows (for
                    fixing corrupt data). If False, only update price-derived
                    fields — snapshot association and quantity are immutable.
        """
        result = ValuationResult()
        result.start_date = start_date
        result.end_date = end_date

        # Process all accounts — inactive accounts still need historical
        # gaps filled (the timeline resolution limits DHV to dates with
        # snapshots, so no forward data is created for inactive accounts)
        accounts = db.query(Account).all()
        if not accounts:
            return result

        # Resolve snapshot timelines per account
        account_timelines = self._resolve_account_timelines(
            db, accounts, start_date, end_date
        )

        if not account_timelines:
            return result

        # Collect all symbols across all snapshots
        all_symbols: set[str] = set()
        has_empty_windows = False
        for timeline in account_timelines.values():
            for window in timeline:
                if window.holdings:
                    for h in window.holdings:
                        all_symbols.add(h.ticker)
                else:
                    has_empty_windows = True

        # Resolve sentinel security ID if any window has empty holdings
        zero_balance_security_id: Optional[str] = None
        if has_empty_windows:
            sentinel_sec = SecurityService.ensure_exists(
                db, ZERO_BALANCE_TICKER, name="Zero Balance Sentinel"
            )
            zero_balance_security_id = sentinel_sec.id

        # Filter out cash-equivalent and synthetic symbols — no need to fetch market data
        symbols_to_fetch = [
            s for s in all_symbols
            if s.upper() not in CASH_TICKERS
            and not s.startswith("_MAN:")
            and not s.startswith("_SF:")
            and not s.startswith("_CASH:")
        ]
        result.symbols_fetched = len(symbols_to_fetch)

        # Detect crypto symbols via Security asset classification
        crypto_symbols = self._detect_crypto_symbols(db)

        # Fetch market data for all symbols
        market_data: dict[str, list] = {}
        if symbols_to_fetch:
            try:
                market_data = self.market_data_service.get_price_history(
                    symbols_to_fetch, start_date, end_date,
                    crypto_symbols=crypto_symbols,
                )
            except Exception as e:
                error_msg = f"Market data fetch failed: {e}"
                logger.warning(error_msg)
                result.errors.append(error_msg)

        # Build price lookup with carry-forward
        price_lookup = build_price_lookup(market_data, start_date, end_date)

        # Walk each day and compute values
        rows: list[DailyHoldingValue] = []
        current = start_date
        while current <= end_date:
            day_rows = self._calculate_day(
                current, account_timelines, price_lookup,
                zero_balance_security_id=zero_balance_security_id,
            )
            rows.extend(day_rows)
            current += timedelta(days=1)

        result.dates_calculated = (end_date - start_date).days + 1

        # Transition cleanup: for each (account, date) pair, ensure sentinel
        # and real rows are mutually exclusive
        if rows and zero_balance_security_id:
            sentinel_pairs: set[tuple[str, date]] = set()
            real_pairs: set[tuple[str, date]] = set()
            for row in rows:
                key = (row.account_id, row.valuation_date)
                if row.security_id == zero_balance_security_id:
                    sentinel_pairs.add(key)
                else:
                    real_pairs.add(key)

            # Delete stale real DHVs where we now have sentinel rows
            for account_id, val_date in sentinel_pairs - real_pairs:
                db.query(DailyHoldingValue).filter(
                    DailyHoldingValue.valuation_date == val_date,
                    DailyHoldingValue.account_id == account_id,
                    DailyHoldingValue.security_id != zero_balance_security_id,
                ).delete(synchronize_session="fetch")

            # Delete stale sentinel DHVs where we now have real rows
            for account_id, val_date in real_pairs - sentinel_pairs:
                db.query(DailyHoldingValue).filter(
                    DailyHoldingValue.valuation_date == val_date,
                    DailyHoldingValue.account_id == account_id,
                    DailyHoldingValue.security_id == zero_balance_security_id,
                ).delete(synchronize_session="fetch")

        # Upsert: update existing rows or insert new ones
        if rows:
            written = 0
            for row in rows:
                existing = (
                    db.query(DailyHoldingValue)
                    .filter(
                        DailyHoldingValue.valuation_date == row.valuation_date,
                        DailyHoldingValue.account_id == row.account_id,
                        DailyHoldingValue.security_id == row.security_id,
                    )
                    .first()
                )
                if existing:
                    existing.close_price = row.close_price
                    existing.market_value = row.market_value
                    if repair:
                        existing.quantity = row.quantity
                        existing.account_snapshot_id = row.account_snapshot_id
                else:
                    db.add(row)
                written += 1
            db.commit()
            result.holdings_written = written

        return result

    def _get_start_date(self, db: Session) -> Optional[date]:
        """Find the start date for backfill.

        Uses the minimum of per-account max DHV dates across active accounts,
        so that if ANY active account is behind, backfill starts from that
        point. For active accounts with no DHV rows, falls back to their
        first successful snapshot date.
        """
        active_accounts = (
            db.query(Account).filter(Account.is_active.is_(True)).all()
        )
        if not active_accounts:
            return None

        per_account_maxes: list[date] = []
        for account in active_accounts:
            max_date = (
                db.query(func.max(DailyHoldingValue.valuation_date))
                .filter(DailyHoldingValue.account_id == account.id)
                .scalar()
            )
            if max_date is not None:
                # +1 because max_date already has complete DHV data
                # (all holdings are written atomically per day)
                per_account_maxes.append(max_date + timedelta(days=1))
            else:
                # Account has no DHV — check for first successful snapshot
                first_snap = (
                    db.query(AccountSnapshot)
                    .join(SyncSession)
                    .filter(
                        AccountSnapshot.account_id == account.id,
                        AccountSnapshot.status == "success",
                        SyncSession.is_complete.is_(True),
                    )
                    .order_by(SyncSession.timestamp.asc())
                    .first()
                )
                if first_snap is not None:
                    per_account_maxes.append(
                        self._utc_to_local_date(first_snap.sync_session.timestamp)
                    )

        if not per_account_maxes:
            return None

        return min(per_account_maxes)

    @staticmethod
    def _utc_to_local_date(utc_dt: datetime) -> date:
        """Convert a naive-UTC datetime to a local calendar date.

        SyncSession timestamps are stored as naive UTC in SQLite.
        date.today() returns the local date. We need local dates when
        comparing to avoid off-by-one errors (e.g., 5 PM PT on Feb 10
        is stored as Feb 11 01:00 UTC).
        """
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        return utc_dt.astimezone().date()

    def _resolve_account_timelines(
        self,
        db: Session,
        accounts: list[Account],
        start_date: date,
        end_date: date,
    ) -> dict[str, list[SnapshotWindow]]:
        """For each account, build ordered list of (effective_date, snapshot, holdings).

        Includes the latest snapshot before start_date as the baseline, plus
        all snapshots within the date range. Uses local dates (converted from
        UTC timestamps) to avoid off-by-one errors when the UTC calendar day
        differs from the local calendar day.
        """
        timelines: dict[str, list[SnapshotWindow]] = {}

        for account in accounts:
            # Load all successful snapshots for this account
            all_snaps = (
                db.query(AccountSnapshot)
                .join(SyncSession)
                .filter(
                    AccountSnapshot.account_id == account.id,
                    AccountSnapshot.status == "success",
                )
                .order_by(SyncSession.timestamp.asc())
                .all()
            )

            if not all_snaps:
                continue

            # Classify snapshots using local dates
            baseline_snap = None
            transition_snaps: list[tuple[AccountSnapshot, date]] = []

            for snap in all_snaps:
                local_date = self._utc_to_local_date(snap.sync_session.timestamp)
                if local_date <= start_date:
                    baseline_snap = snap  # keeps latest (ordered asc)
                elif local_date <= end_date:
                    transition_snaps.append((snap, local_date))

            # Build windows (only load holdings for snapshots we'll use)
            windows: list[SnapshotWindow] = []

            if baseline_snap:
                holdings = self._load_holdings(db, baseline_snap.id)
                windows.append(SnapshotWindow(
                    effective_date=start_date,
                    account_snapshot_id=baseline_snap.id,
                    holdings=holdings,
                ))

            for acct_snap, local_date in transition_snaps:
                holdings = self._load_holdings(db, acct_snap.id)
                windows.append(SnapshotWindow(
                    effective_date=local_date,
                    account_snapshot_id=acct_snap.id,
                    holdings=holdings,
                ))

            if windows:
                timelines[account.id] = windows

        return timelines

    def _load_holdings(
        self, db: Session, account_snapshot_id: str
    ) -> list[HoldingSummary]:
        """Load holdings for a specific account snapshot."""
        holdings = (
            db.query(Holding)
            .filter(Holding.account_snapshot_id == account_snapshot_id)
            .all()
        )
        return [
            HoldingSummary(
                ticker=h.ticker,
                security_id=h.security_id,
                quantity=Decimal(str(h.quantity)),
                snapshot_price=Decimal(str(h.snapshot_price)),
            )
            for h in holdings
        ]

    def _calculate_day(
        self,
        target_date: date,
        account_timelines: dict[str, list[SnapshotWindow]],
        price_lookup: dict[str, dict[date, Decimal]],
        zero_balance_security_id: Optional[str] = None,
    ) -> list[DailyHoldingValue]:
        """Compute all holding values for a single day across all accounts."""
        rows: list[DailyHoldingValue] = []

        for account_id, windows in account_timelines.items():
            # Find the latest snapshot window on or before target_date
            active_window: Optional[SnapshotWindow] = None
            for window in windows:
                if window.effective_date <= target_date:
                    active_window = window
                else:
                    break

            if active_window is None:
                continue

            if not active_window.holdings and zero_balance_security_id:
                # Empty window — emit a sentinel $0 row
                rows.append(DailyHoldingValue(
                    valuation_date=target_date,
                    account_id=account_id,
                    account_snapshot_id=active_window.account_snapshot_id,
                    security_id=zero_balance_security_id,
                    ticker=ZERO_BALANCE_TICKER,
                    quantity=Decimal("0"),
                    close_price=Decimal("0"),
                    market_value=Decimal("0"),
                ))
                continue

            for holding in active_window.holdings:
                price = self._get_price_for_holding(
                    price_lookup, holding.ticker, target_date,
                    holding.snapshot_price,
                )
                market_value = (holding.quantity * price).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

                rows.append(DailyHoldingValue(
                    valuation_date=target_date,
                    account_id=account_id,
                    account_snapshot_id=active_window.account_snapshot_id,
                    security_id=holding.security_id,
                    ticker=holding.ticker,
                    quantity=holding.quantity,
                    close_price=price,
                    market_value=market_value,
                ))

        return rows

    @staticmethod
    def _get_price_for_holding(
        price_lookup: dict[str, dict[date, Decimal]],
        ticker: str,
        target_date: date,
        snapshot_price: Decimal,
    ) -> Decimal:
        """Get the best available price for a holding on a given date."""
        if is_cash_equivalent(ticker, snapshot_price):
            return Decimal("1")

        symbol_prices = price_lookup.get(ticker, {})
        if target_date in symbol_prices:
            return symbol_prices[target_date]

        # Fall back to snapshot price
        return snapshot_price

    @staticmethod
    def _detect_crypto_symbols(db: Session) -> Optional[set[str]]:
        """Detect which tickers are classified as crypto.

        Queries the AssetClass table for a "Crypto" class, then finds
        all Security records assigned to it. Returns their tickers as
        a set, or None if no "Crypto" asset class exists.
        """
        crypto_class = (
            db.query(AssetClass)
            .filter(AssetClass.name == "Crypto")
            .first()
        )
        if crypto_class is None:
            return None

        securities = (
            db.query(Security)
            .filter(Security.manual_asset_class_id == crypto_class.id)
            .all()
        )
        if not securities:
            return None

        tickers = {s.ticker for s in securities}
        if tickers:
            logger.info(
                "Detected %d crypto symbols via asset classification: %s",
                len(tickers), ", ".join(sorted(tickers)),
            )
        return tickers
