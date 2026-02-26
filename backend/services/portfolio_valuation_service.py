"""Portfolio valuation service — computes and stores daily holding values."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from models import Account, AccountSnapshot, DailyHoldingValue, Holding, SyncSession
from models.asset_class import AssetClass
from models.security import Security
from services.market_data_service import MarketDataService
from services.security_service import SecurityService
from utils.ticker import SYNTHETIC_PREFIX, ZERO_BALANCE_TICKER

logger = logging.getLogger(__name__)

# Calendar days before a carry-forward price is considered stale (~5 trading days).
STALE_PRICE_DAYS = 7

# --- Price source constants ---
PRICE_SOURCE_MARKET = "market"
PRICE_SOURCE_SNAPSHOT = "snapshot"
PRICE_SOURCE_CARRY_FORWARD = "carry_forward"
PRICE_SOURCE_CORRECTED = "corrected"
PRICE_SOURCE_CASH = "cash"

# --- Price guard thresholds ---
# New/prior price ratio bands: prices outside these bounds are rejected.
EQUITY_PRICE_BAND = (Decimal("0.05"), Decimal("20"))
CRYPTO_PRICE_BAND = (Decimal("0.01"), Decimal("100"))

# --- Retrospective validation constants ---
RETRO_TRAILING_CALENDAR_DAYS = 7  # ~5 trading days
RETRO_EQUITY_THRESHOLD = Decimal("0.01")  # 1% deviation
RETRO_CRYPTO_THRESHOLD = Decimal("0.05")  # 5% deviation


class PriceWithDate(NamedTuple):
    """A close price paired with the actual trading date and source."""

    price: Decimal
    price_date: date
    source: str


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
    corrections: int = 0  # TODO: surface via diagnostics API endpoint
    correction_details: list[str] = field(default_factory=list)


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
) -> dict[str, dict[date, PriceWithDate]]:
    """Build a symbol -> date -> PriceWithDate mapping with carry-forward.

    For each calendar day in the range, if no price exists for that day,
    the most recent prior price is used. This handles weekends, holidays,
    and symbols with sparse data.  The ``price_date`` field on each entry
    records the actual trading date the close price came from, so callers
    can detect stale carry-forwards.  The ``source`` field is tagged as
    ``PRICE_SOURCE_MARKET`` when the price is from the actual trading day,
    or ``PRICE_SOURCE_CARRY_FORWARD`` when carried from a prior day.
    """
    lookup: dict[str, dict[date, PriceWithDate]] = {}

    for symbol, prices in market_data.items():
        sorted_prices = sorted(prices, key=lambda p: p.price_date)

        price_map: dict[date, PriceWithDate] = {}
        last_price: Optional[Decimal] = None
        last_price_date: Optional[date] = None
        price_idx = 0

        current = start_date
        while current <= end_date:
            while (
                price_idx < len(sorted_prices)
                and sorted_prices[price_idx].price_date <= current
            ):
                last_price = sorted_prices[price_idx].close_price
                last_price_date = sorted_prices[price_idx].price_date
                price_idx += 1

            if last_price is not None and last_price_date is not None:
                source = (
                    PRICE_SOURCE_MARKET
                    if last_price_date == current
                    else PRICE_SOURCE_CARRY_FORWARD
                )
                price_map[current] = PriceWithDate(last_price, last_price_date, source)

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
            is_cash = is_cash_equivalent(h.ticker, h.snapshot_price)
            source = PRICE_SOURCE_CASH if is_cash else PRICE_SOURCE_SNAPSHOT

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
                existing.price_date = valuation_date
                existing.price_source = source
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
                    price_date=valuation_date,
                    price_source=source,
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
            existing.price_date = valuation_date
            existing.price_source = PRICE_SOURCE_CASH
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
            price_date=valuation_date,
            price_source=PRICE_SOURCE_CASH,
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
        """Analyze DHV gaps and stale prices for each active account.

        Returns a list of per-account diagnostics with:
        - account_id, account_name
        - expected_start, expected_end (first snapshot → yesterday)
        - expected_days, actual_days, missing_days
        - missing_dates (list, capped at 100)
        - stale_price_count, stale_prices (holdings with stale carry-forward prices)
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

            # Detect stale carry-forward prices on the latest valuation date.
            # Excludes synthetic tickers (_SYN:*) — these are non-tradable
            # holdings (real estate, vehicles, etc.) with no market price to
            # go stale; the user sets a value manually.
            stale_prices: list[dict] = []
            if actual_dates:
                latest_val_date = max(actual_dates)
                stale_q = (
                    db.query(DailyHoldingValue)
                    .options(joinedload(DailyHoldingValue.security))
                    .filter(
                        DailyHoldingValue.account_id == account.id,
                        DailyHoldingValue.valuation_date == latest_val_date,
                        DailyHoldingValue.price_date.isnot(None),
                        ~DailyHoldingValue.ticker.like(
                            SYNTHETIC_PREFIX.replace("_", r"\_") + "%",
                            escape="\\",
                        ),
                    )
                )
                if sentinel_id:
                    stale_q = stale_q.filter(
                        DailyHoldingValue.security_id != sentinel_id
                    )
                for dhv_row in stale_q.all():
                    age = (dhv_row.valuation_date - dhv_row.price_date).days
                    if age > STALE_PRICE_DAYS:
                        sec = dhv_row.security
                        stale_prices.append({
                            "ticker": dhv_row.ticker,
                            "security_name": sec.name if sec else None,
                            "price_date": dhv_row.price_date,
                            "age_days": age,
                            "close_price": dhv_row.close_price,
                            "market_value": dhv_row.market_value,
                            "price_source": dhv_row.price_source,
                        })

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
                "stale_price_count": len(stale_prices),
                "stale_prices": stale_prices,
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
            and not s.startswith("_SYN:")
            and not s.startswith("_CASH:")
        ]
        result.symbols_fetched = len(symbols_to_fetch)

        # Detect crypto symbols via Security asset classification
        crypto_symbols = self._detect_crypto_symbols(db)

        # Extend fetch range by RETRO_TRAILING_CALENDAR_DAYS so the same
        # market_data dict serves both forward calculation and retrospective
        # validation, avoiding a second API call.
        retro_fetch_start = start_date - timedelta(days=RETRO_TRAILING_CALENDAR_DAYS)

        # Fetch market data for all symbols
        market_data: dict[str, list] = {}
        if symbols_to_fetch:
            try:
                market_data = self.market_data_service.get_price_history(
                    symbols_to_fetch, retro_fetch_start, end_date,
                    crypto_symbols=crypto_symbols,
                )
            except Exception as e:
                error_msg = f"Market data fetch failed: {e}"
                logger.warning(error_msg)
                result.errors.append(error_msg)

        # Retrospective validation: correct prior DHV rows using fresh market data.
        # Must run before _load_prior_closes so corrected prices for
        # (start_date - 1) are visible via SQLAlchemy autoflush.
        account_ids = list(account_timelines.keys())
        self._retrospective_validate(
            db, start_date, market_data, account_ids, crypto_symbols, result,
        )

        # Build price lookup with carry-forward (for the backfill range only)
        price_lookup = build_price_lookup(market_data, start_date, end_date)

        # Pre-load prior closes for price guards
        prior_closes = self._load_prior_closes(db, start_date, account_ids)

        # Walk each day and compute values
        rows: list[DailyHoldingValue] = []
        current = start_date
        while current <= end_date:
            day_rows = self._calculate_day(
                current, account_timelines, price_lookup,
                zero_balance_security_id=zero_balance_security_id,
                prior_closes=prior_closes,
                crypto_symbols=crypto_symbols,
            )
            rows.extend(day_rows)

            # Update prior_closes progressively for multi-day backfills.
            # Note: if a price guard rejected today's market price and fell
            # back to a snapshot price, that snapshot price becomes tomorrow's
            # prior_close. This is intentional — the snapshot is the best
            # available price and will be corrected by retro validation on
            # the next backfill run.
            for row in day_rows:
                if row.close_price and row.close_price > 0:
                    prior_closes[(row.account_id, row.ticker)] = row.close_price

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
                    existing.price_date = row.price_date
                    existing.price_source = row.price_source
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
        price_lookup: dict[str, dict[date, PriceWithDate]],
        zero_balance_security_id: Optional[str] = None,
        prior_closes: Optional[dict[tuple[str, str], Decimal]] = None,
        crypto_symbols: Optional[set[str]] = None,
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
                    price_date=target_date,
                    price_source=PRICE_SOURCE_CASH,
                ))
                continue

            for holding in active_window.holdings:
                price_info = self._get_price_for_holding(
                    price_lookup, holding.ticker, target_date,
                    holding.snapshot_price,
                    snapshot_effective_date=active_window.effective_date,
                )

                # Apply price guards for non-cash sources
                if price_info.source != PRICE_SOURCE_CASH:
                    prior_close = (
                        prior_closes.get((account_id, holding.ticker))
                        if prior_closes else None
                    )
                    is_crypto = (
                        crypto_symbols is not None
                        and holding.ticker in crypto_symbols
                    )
                    price_info = self._validate_price(
                        price_info,
                        holding.ticker,
                        target_date,
                        holding.snapshot_price,
                        snapshot_effective_date=active_window.effective_date,
                        prior_close=prior_close,
                        is_crypto=is_crypto,
                    )

                market_value = (holding.quantity * price_info.price).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

                rows.append(DailyHoldingValue(
                    valuation_date=target_date,
                    account_id=account_id,
                    account_snapshot_id=active_window.account_snapshot_id,
                    security_id=holding.security_id,
                    ticker=holding.ticker,
                    quantity=holding.quantity,
                    close_price=price_info.price,
                    market_value=market_value,
                    price_date=price_info.price_date,
                    price_source=price_info.source,
                ))

        return rows

    @staticmethod
    def _get_price_for_holding(
        price_lookup: dict[str, dict[date, PriceWithDate]],
        ticker: str,
        target_date: date,
        snapshot_price: Decimal,
        snapshot_effective_date: Optional[date] = None,
    ) -> PriceWithDate:
        """Get the best available price for a holding on a given date.

        Returns a ``PriceWithDate`` so callers can record the actual
        trading date of the price used.
        """
        if is_cash_equivalent(ticker, snapshot_price):
            return PriceWithDate(Decimal("1"), target_date, PRICE_SOURCE_CASH)

        symbol_prices = price_lookup.get(ticker, {})
        if target_date in symbol_prices:
            return symbol_prices[target_date]

        # Fall back to snapshot price
        fallback_date = snapshot_effective_date if snapshot_effective_date is not None else target_date
        return PriceWithDate(snapshot_price, fallback_date, PRICE_SOURCE_SNAPSHOT)

    @staticmethod
    def _validate_price(
        price_info: PriceWithDate,
        ticker: str,
        target_date: date,
        snapshot_price: Decimal,
        snapshot_effective_date: Optional[date] = None,
        prior_close: Optional[Decimal] = None,
        is_crypto: bool = False,
    ) -> PriceWithDate:
        """Validate a market price against basic sanity guards.

        Guards (in order):
        1. Reject price <= 0 → return snapshot fallback
        2. If prior_close exists and is >0: check ratio against band
        3. Otherwise pass through unchanged
        """
        price = price_info.price

        # Guard 1: reject zero or negative
        if price <= 0:
            logger.warning(
                "Price guard: %s on %s has non-positive price %s, "
                "falling back to snapshot price %s",
                ticker, target_date, price, snapshot_price,
            )
            fallback_date = (
                snapshot_effective_date
                if snapshot_effective_date is not None
                else target_date
            )
            return PriceWithDate(snapshot_price, fallback_date, PRICE_SOURCE_SNAPSHOT)

        # Guard 2: ratio check against prior close
        if prior_close is not None and prior_close > 0:
            ratio = price / prior_close
            band = CRYPTO_PRICE_BAND if is_crypto else EQUITY_PRICE_BAND
            low, high = band

            if ratio < low or ratio > high:
                logger.warning(
                    "Price guard: %s on %s has suspicious ratio %.4f "
                    "(price=%s, prior=%s, band=%s-%s), "
                    "falling back to snapshot price %s",
                    ticker, target_date, ratio, price, prior_close,
                    low, high, snapshot_price,
                )
                fallback_date = (
                    snapshot_effective_date
                    if snapshot_effective_date is not None
                    else target_date
                )
                return PriceWithDate(
                    snapshot_price, fallback_date, PRICE_SOURCE_SNAPSHOT
                )

        return price_info

    @staticmethod
    def _load_prior_closes(
        db: Session,
        start_date: date,
        account_ids: list[str],
    ) -> dict[tuple[str, str], Decimal]:
        """Load prior day closes for price guard ratio checks.

        Returns a dict of (account_id, ticker) -> close_price for the day
        before start_date.

        Uses exactly 1-day lookback (not a wider window) because DHV rows
        are built for every calendar day — including weekends and holidays —
        so the previous calendar day always has data if the account has any
        history.  If no row exists (e.g. first-ever backfill), the key is
        simply absent and the ratio check in _validate_price() is skipped.
        """
        if not account_ids:
            return {}
        prior_date = start_date - timedelta(days=1)
        rows = (
            db.query(
                DailyHoldingValue.account_id,
                DailyHoldingValue.ticker,
                DailyHoldingValue.close_price,
            )
            .filter(
                DailyHoldingValue.valuation_date == prior_date,
                DailyHoldingValue.account_id.in_(account_ids),
            )
            .all()
        )
        return {
            (row.account_id, row.ticker): Decimal(str(row.close_price))
            for row in rows
        }

    def _retrospective_validate(
        self,
        db: Session,
        start_date: date,
        market_data: dict[str, list],
        account_ids: list[str],
        crypto_symbols: Optional[set[str]],
        result: ValuationResult,
    ) -> None:
        """Correct prior DHV rows using fresh market data.

        Looks back RETRO_TRAILING_CALENDAR_DAYS before start_date and
        corrects rows where the stored price differs from fresh market data.

        Rows with PRICE_SOURCE_CORRECTED are permanently frozen — skipped
        to prevent re-correction loops. The original price and source are
        not preserved separately; corrections are logged at INFO but not
        persisted as an audit trail. If a correction is wrong, a re-sync
        from the brokerage API is required to restore the original value.
        """
        if not market_data:
            return

        retro_end = start_date - timedelta(days=1)
        retro_start = start_date - timedelta(days=RETRO_TRAILING_CALENDAR_DAYS)

        if retro_start > retro_end:
            return

        # Build retro lookup from the same market_data (already fetched
        # with extended range)
        retro_lookup = build_price_lookup(market_data, retro_start, retro_end)

        # Query stored DHV rows in the retro window
        stored_rows = (
            db.query(DailyHoldingValue)
            .filter(
                DailyHoldingValue.valuation_date >= retro_start,
                DailyHoldingValue.valuation_date <= retro_end,
                DailyHoldingValue.account_id.in_(account_ids),
            )
            .all()
        )

        for dhv in stored_rows:
            # Skip cash, sentinels, synthetic tickers
            if dhv.ticker.upper() in CASH_TICKERS or dhv.ticker.startswith("_CASH:"):
                continue
            if dhv.ticker == ZERO_BALANCE_TICKER:
                continue
            if dhv.ticker.startswith(SYNTHETIC_PREFIX):
                continue

            # Look up fresh market price
            symbol_prices = retro_lookup.get(dhv.ticker, {})
            fresh = symbol_prices.get(dhv.valuation_date)
            if fresh is None:
                continue

            # Only use actual market data, not carry-forward
            if fresh.source != PRICE_SOURCE_MARKET:
                continue

            stored_source = dhv.price_source
            stored_price = Decimal(str(dhv.close_price))
            fresh_price = fresh.price

            # Decide whether to correct
            should_correct = False

            if stored_source in (
                PRICE_SOURCE_SNAPSHOT,
                PRICE_SOURCE_CARRY_FORWARD,
                None,
            ):
                # Always correct snapshot, carry-forward, or legacy (NULL)
                should_correct = True
            elif stored_source == PRICE_SOURCE_MARKET:
                # Threshold correct: only if deviation exceeds threshold
                if stored_price > 0:
                    deviation = abs(fresh_price - stored_price) / stored_price
                    is_crypto = (
                        crypto_symbols is not None
                        and dhv.ticker in crypto_symbols
                    )
                    threshold = (
                        RETRO_CRYPTO_THRESHOLD if is_crypto
                        else RETRO_EQUITY_THRESHOLD
                    )
                    if deviation > threshold:
                        should_correct = True
            elif stored_source == PRICE_SOURCE_CORRECTED:
                # Permanently frozen — never re-correct
                continue

            if should_correct:
                old_price = stored_price
                old_mv = Decimal(str(dhv.market_value))
                qty = Decimal(str(dhv.quantity))

                dhv.close_price = fresh_price
                dhv.price_date = fresh.price_date
                dhv.price_source = PRICE_SOURCE_CORRECTED
                dhv.market_value = (qty * fresh_price).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

                detail = (
                    f"Corrected {dhv.ticker} on {dhv.valuation_date}: "
                    f"price {old_price}->{fresh_price}, "
                    f"mv {old_mv}->{dhv.market_value}, "
                    f"source {stored_source}->{PRICE_SOURCE_CORRECTED}"
                )
                logger.info(detail)
                result.corrections += 1
                result.correction_details.append(detail)

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
