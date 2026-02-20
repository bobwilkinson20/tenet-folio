"""Unit tests for the portfolio valuation service."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from integrations.market_data_protocol import PriceResult
from models import Account, AccountSnapshot, DailyHoldingValue, Holding, SyncSession
from services.market_data_service import MarketDataService
from models import Security
from models.asset_class import AssetClass
from services.portfolio_valuation_service import (
    CASH_TICKERS,
    HoldingSummary,
    PortfolioValuationService,
    SnapshotWindow,
    build_price_lookup,
    is_cash_equivalent,
)
from tests.fixtures import get_or_create_security
from utils.ticker import ZERO_BALANCE_TICKER


# ---------------------------------------------------------------------------
# Mock market data provider
# ---------------------------------------------------------------------------
class MockMarketDataProvider:
    """Returns deterministic prices for testing."""

    def __init__(self, prices: dict[str, dict[date, Decimal]]):
        self._prices = prices

    @property
    def provider_name(self) -> str:
        return "mock"

    def get_price_history(
        self, symbols: list[str], start_date: date, end_date: date
    ) -> dict[str, list[PriceResult]]:
        result: dict[str, list[PriceResult]] = {}
        for symbol in symbols:
            symbol_prices = self._prices.get(symbol, {})
            result[symbol] = [
                PriceResult(
                    symbol=symbol,
                    price_date=d,
                    close_price=p,
                    source="mock",
                )
                for d, p in sorted(symbol_prices.items())
                if start_date <= d <= end_date
            ]
        return result


def _make_mock_service(
    prices: dict[str, dict[date, Decimal]],
) -> PortfolioValuationService:
    """Create a valuation service with mock market data."""
    provider = MockMarketDataProvider(prices)
    mds = MarketDataService(provider=provider)
    return PortfolioValuationService(market_data_service=mds)


# ---------------------------------------------------------------------------
# Helpers to set up DB fixtures
# ---------------------------------------------------------------------------
def _create_account(db: Session, name: str = "Test Account", **kwargs) -> Account:
    acc = Account(
        provider_name=kwargs.get("provider_name", "SnapTrade"),
        external_id=kwargs.get("external_id", f"ext_{name}"),
        name=name,
        is_active=kwargs.get("is_active", True),
    )
    db.add(acc)
    db.flush()
    return acc


def _create_sync_session(
    db: Session,
    ts: datetime,
    is_complete: bool = True,
) -> SyncSession:
    sync_session = SyncSession(timestamp=ts, is_complete=is_complete)
    db.add(sync_session)
    db.flush()
    return sync_session


def _create_account_snapshot(
    db: Session,
    account: Account,
    sync_session: SyncSession,
    status: str = "success",
    total_value: Decimal = Decimal("0"),
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


def _create_holding(
    db: Session,
    sync_session: SyncSession,
    account: Account,
    ticker: str,
    quantity: Decimal,
    price: Decimal,
    account_snapshot: AccountSnapshot | None = None,
) -> Holding:
    security = get_or_create_security(db, ticker)
    h = Holding(
        account_snapshot_id=account_snapshot.id if account_snapshot else None,
        security_id=security.id,
        ticker=ticker,
        quantity=quantity,
        snapshot_price=price,
        snapshot_value=quantity * price,
    )
    db.add(h)
    db.flush()
    return h


# ---------------------------------------------------------------------------
# Tests: build_price_lookup
# ---------------------------------------------------------------------------
class TestBuildPriceLookup:
    """Tests for the price lookup builder with carry-forward logic."""

    def test_basic_trading_days(self):
        """Trading day prices are mapped correctly."""
        market_data = {
            "AAPL": [
                PriceResult("AAPL", date(2025, 1, 6), Decimal("150"), "mock"),
                PriceResult("AAPL", date(2025, 1, 7), Decimal("152"), "mock"),
            ]
        }
        lookup = build_price_lookup(
            market_data, date(2025, 1, 6), date(2025, 1, 7)
        )
        assert lookup["AAPL"][date(2025, 1, 6)] == Decimal("150")
        assert lookup["AAPL"][date(2025, 1, 7)] == Decimal("152")

    def test_carry_forward_over_weekend(self):
        """Friday's price carries forward through Saturday and Sunday."""
        market_data = {
            "AAPL": [
                PriceResult("AAPL", date(2025, 1, 3), Decimal("150"), "mock"),  # Fri
                PriceResult("AAPL", date(2025, 1, 6), Decimal("155"), "mock"),  # Mon
            ]
        }
        lookup = build_price_lookup(
            market_data, date(2025, 1, 3), date(2025, 1, 6)
        )
        assert lookup["AAPL"][date(2025, 1, 3)] == Decimal("150")
        assert lookup["AAPL"][date(2025, 1, 4)] == Decimal("150")  # Sat
        assert lookup["AAPL"][date(2025, 1, 5)] == Decimal("150")  # Sun
        assert lookup["AAPL"][date(2025, 1, 6)] == Decimal("155")

    def test_carry_forward_over_holiday(self):
        """Holiday gap is filled with the prior close."""
        market_data = {
            "AAPL": [
                PriceResult("AAPL", date(2025, 1, 2), Decimal("148"), "mock"),
                # Jan 3 is a gap (holiday)
                PriceResult("AAPL", date(2025, 1, 6), Decimal("150"), "mock"),
            ]
        }
        lookup = build_price_lookup(
            market_data, date(2025, 1, 2), date(2025, 1, 6)
        )
        assert lookup["AAPL"][date(2025, 1, 3)] == Decimal("148")
        assert lookup["AAPL"][date(2025, 1, 4)] == Decimal("148")
        assert lookup["AAPL"][date(2025, 1, 5)] == Decimal("148")

    def test_no_data_for_symbol(self):
        """Symbol with no prices results in empty lookup."""
        market_data = {"AAPL": []}
        lookup = build_price_lookup(
            market_data, date(2025, 1, 6), date(2025, 1, 7)
        )
        assert lookup["AAPL"] == {}

    def test_partial_data_starts_mid_range(self):
        """Symbol that starts mid-range has no prices for earlier days."""
        market_data = {
            "AAPL": [
                PriceResult("AAPL", date(2025, 1, 8), Decimal("155"), "mock"),
            ]
        }
        lookup = build_price_lookup(
            market_data, date(2025, 1, 6), date(2025, 1, 9)
        )
        assert date(2025, 1, 6) not in lookup["AAPL"]
        assert date(2025, 1, 7) not in lookup["AAPL"]
        assert lookup["AAPL"][date(2025, 1, 8)] == Decimal("155")
        assert lookup["AAPL"][date(2025, 1, 9)] == Decimal("155")

    def test_multiple_symbols(self):
        """Multiple symbols are tracked independently."""
        market_data = {
            "AAPL": [
                PriceResult("AAPL", date(2025, 1, 6), Decimal("150"), "mock"),
            ],
            "GOOG": [
                PriceResult("GOOG", date(2025, 1, 6), Decimal("2800"), "mock"),
            ],
        }
        lookup = build_price_lookup(
            market_data, date(2025, 1, 6), date(2025, 1, 6)
        )
        assert lookup["AAPL"][date(2025, 1, 6)] == Decimal("150")
        assert lookup["GOOG"][date(2025, 1, 6)] == Decimal("2800")


# ---------------------------------------------------------------------------
# Tests: is_cash_equivalent
# ---------------------------------------------------------------------------
class TestIsCashEquivalent:
    """Tests for cash equivalent detection."""

    def test_known_cash_tickers(self):
        for ticker in CASH_TICKERS:
            assert is_cash_equivalent(ticker, Decimal("1")) is True

    def test_case_insensitive(self):
        assert is_cash_equivalent("usd", Decimal("1")) is True
        assert is_cash_equivalent("Spaxx", Decimal("1")) is True

    def test_price_heuristic_removed(self):
        """Price == $1 no longer triggers cash equivalent detection."""
        assert is_cash_equivalent("UNKNOWN_FUND", Decimal("1")) is False
        # This prevents false positives for stocks/bonds trading at $1.00

    def test_non_cash_ticker(self):
        assert is_cash_equivalent("AAPL", Decimal("150")) is False

    def test_non_cash_price_not_one(self):
        assert is_cash_equivalent("VTI", Decimal("250.50")) is False

    def test_cash_prefix_recognized(self):
        """_CASH: prefixed tickers are treated as cash equivalents."""
        assert is_cash_equivalent("_CASH:USD", Decimal("1")) is True
        assert is_cash_equivalent("_CASH:CAD", Decimal("1")) is True
        # Price doesn't matter for _CASH: prefix
        assert is_cash_equivalent("_CASH:USD", Decimal("1.0")) is True


# ---------------------------------------------------------------------------
# Tests: PortfolioValuationService.backfill
# ---------------------------------------------------------------------------
class TestBackfill:
    """Tests for the main backfill method."""

    def test_no_sync_sessions(self, db: Session):
        """No sync sessions -> no-op, returns empty result."""
        service = _make_mock_service({})
        result = service.backfill(db)
        assert result.dates_calculated == 0
        assert result.holdings_written == 0
        assert result.start_date is None

    def test_already_current(self, db: Session):
        """Last valuation is yesterday -> no-op (no market data fetch)."""
        yesterday = date.today() - timedelta(days=1)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime(2025, 1, 1, tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        # Manually insert a valuation for yesterday
        security = get_or_create_security(db, "AAPL")
        dhv = DailyHoldingValue(
            valuation_date=yesterday,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("150"),
            market_value=Decimal("1500"),
        )
        db.add(dhv)
        db.commit()

        service = _make_mock_service({"AAPL": {yesterday: Decimal("155")}})
        result = service.backfill(db)
        # Data is current through yesterday — skip entirely
        assert result.dates_calculated == 0
        assert result.holdings_written == 0

        # Existing row is untouched
        rows = db.query(DailyHoldingValue).all()
        assert len(rows) == 1
        assert rows[0].close_price == Decimal("150")

    def test_single_day_backfill(self, db: Session):
        """One day gap -> calculates one day (plus reprocesses last existing)."""
        yesterday = date.today() - timedelta(days=1)
        snap_date = yesterday - timedelta(days=1)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(snap_date, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        # Already have valuation through day before yesterday
        security = get_or_create_security(db, "AAPL")
        dhv = DailyHoldingValue(
            valuation_date=snap_date,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("150"),
            market_value=Decimal("1500"),
        )
        db.add(dhv)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        result = service.backfill(db)

        assert result.dates_calculated == 1  # only yesterday (snap_date already has DHV)
        assert result.holdings_written == 1
        assert result.start_date == yesterday
        assert result.end_date == yesterday

        # Verify the written row
        row = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.valuation_date == yesterday)
            .first()
        )
        assert row is not None
        assert row.ticker == "AAPL"
        assert row.close_price == Decimal("155")
        assert row.market_value == Decimal("1550.00")

    def test_multi_day_backfill(self, db: Session):
        """Multi-day gap calculates all days."""
        yesterday = date.today() - timedelta(days=1)
        start = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(
            start, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        prices = {
            "AAPL": {
                start: Decimal("150"),
                start + timedelta(days=1): Decimal("152"),
                yesterday: Decimal("155"),
            }
        }
        service = _make_mock_service(prices)
        result = service.backfill(db)

        assert result.dates_calculated == 3
        assert result.holdings_written == 3

    def test_sync_session_transition(self, db: Session):
        """When a new sync session arrives mid-range, switch to its holdings."""
        yesterday = date.today() - timedelta(days=1)
        day1 = yesterday - timedelta(days=2)
        day2 = yesterday - timedelta(days=1)

        account = _create_account(db)

        # First sync session on day1: holds AAPL
        sync_session_1 = _create_sync_session(
            db, datetime.combine(day1, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap1 = _create_account_snapshot(db, account, sync_session_1)
        _create_holding(db, sync_session_1, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap1)

        # Second sync session on day2: holds GOOG instead
        sync_session_2 = _create_sync_session(
            db, datetime.combine(day2, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap2 = _create_account_snapshot(db, account, sync_session_2)
        _create_holding(db, sync_session_2, account, "GOOG", Decimal("5"), Decimal("2800"), acct_snap2)
        db.commit()

        prices = {
            "AAPL": {
                day1: Decimal("150"),
                day2: Decimal("152"),
                yesterday: Decimal("155"),
            },
            "GOOG": {
                day1: Decimal("2800"),
                day2: Decimal("2850"),
                yesterday: Decimal("2900"),
            },
        }
        service = _make_mock_service(prices)
        service.backfill(db)

        # Day1 uses sync_session_1 (AAPL), day2 and yesterday use sync_session_2 (GOOG)
        aapl_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.ticker == "AAPL")
            .all()
        )
        goog_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.ticker == "GOOG")
            .all()
        )
        assert len(aapl_rows) == 1
        assert aapl_rows[0].valuation_date == day1
        assert len(goog_rows) == 2

    def test_cash_handling(self, db: Session):
        """Cash tickers get $1.00 price regardless of market data."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(
            db, sync_session, account, "USD", Decimal("5000"), Decimal("1"), acct_snap
        )
        db.commit()

        # No market data needed for cash
        service = _make_mock_service({})
        service.backfill(db)

        row = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.ticker == "USD")
            .first()
        )
        assert row is not None
        assert row.close_price == Decimal("1")
        assert row.market_value == Decimal("5000.00")

    def test_money_market_fund_handling(self, db: Session):
        """Money market funds (price == $1) treated as cash."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(
            db, sync_session, account, "SPAXX", Decimal("10000"), Decimal("1"), acct_snap
        )
        db.commit()

        service = _make_mock_service({})
        service.backfill(db)

        row = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.ticker == "SPAXX")
            .first()
        )
        assert row is not None
        assert row.close_price == Decimal("1")
        assert row.market_value == Decimal("10000.00")

    def test_missing_market_data_fallback(self, db: Session):
        """Unknown ticker falls back to snapshot price."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(
            db, sync_session, account, "PRIVCO", Decimal("100"), Decimal("25.50"), acct_snap
        )
        db.commit()

        # No market data for PRIVCO
        service = _make_mock_service({})
        service.backfill(db)

        row = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.ticker == "PRIVCO")
            .first()
        )
        assert row is not None
        assert row.close_price == Decimal("25.50")
        assert row.market_value == Decimal("2550.00")

    def test_multiple_accounts(self, db: Session):
        """Values calculated independently per account."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        acct1 = _create_account(db, name="Account 1", external_id="ext_1")
        acct2 = _create_account(db, name="Account 2", external_id="ext_2")
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap1 = _create_account_snapshot(db, acct1, sync_session)
        acct_snap2 = _create_account_snapshot(db, acct2, sync_session)
        _create_holding(db, sync_session, acct1, "AAPL", Decimal("10"), Decimal("150"), acct_snap1)
        _create_holding(db, sync_session, acct2, "AAPL", Decimal("20"), Decimal("150"), acct_snap2)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        service.backfill(db)

        rows = db.query(DailyHoldingValue).all()
        assert len(rows) == 2
        values = {r.account_snapshot_id: r.market_value for r in rows}
        assert values[acct_snap1.id] == Decimal("1550.00")
        assert values[acct_snap2.id] == Decimal("3100.00")

    def test_inactive_account_gets_historical_dhv(self, db: Session):
        """Inactive accounts get DHV for historical snapshot dates."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        # Active account
        active = _create_account(
            db, name="Active", external_id="ext_active", is_active=True
        )
        # Inactive account -- still has snapshots from when it was active
        inactive = _create_account(
            db, name="Inactive", external_id="ext_inactive", is_active=False
        )
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap_active = _create_account_snapshot(db, active, sync_session)
        acct_snap_inactive = _create_account_snapshot(db, inactive, sync_session)
        _create_holding(db, sync_session, active, "AAPL", Decimal("10"), Decimal("150"), acct_snap_active)
        _create_holding(db, sync_session, inactive, "VTI", Decimal("5"), Decimal("250"), acct_snap_inactive)
        db.commit()

        prices = {
            "AAPL": {yesterday: Decimal("155")},
            "VTI": {yesterday: Decimal("255")},
        }
        service = _make_mock_service(prices)
        service.backfill(db)

        # Both accounts get valuations — inactive accounts still get
        # historical DHV filled for dates with snapshots
        rows = db.query(DailyHoldingValue).all()
        assert len(rows) == 2
        tickers = {r.ticker for r in rows}
        assert tickers == {"AAPL", "VTI"}

    def test_idempotent_backfill(self, db: Session):
        """Running backfill twice updates existing rows, doesn't duplicate."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)

        result1 = service.backfill(db)
        assert result1.holdings_written == 1

        # Second run skips — data already current through yesterday
        result2 = service.backfill(db)
        assert result2.dates_calculated == 0
        assert result2.holdings_written == 0

        # Still only 1 row (no duplicate)
        rows = db.query(DailyHoldingValue).all()
        assert len(rows) == 1

    def test_no_baseline_sync_session_for_account(self, db: Session):
        """Account with first sync session after start_date is excluded for earlier days."""
        yesterday = date.today() - timedelta(days=1)
        day1 = yesterday - timedelta(days=1)

        acct1 = _create_account(db, name="Early", external_id="ext_early")
        acct2 = _create_account(db, name="Late", external_id="ext_late")

        # acct1 has a sync session on day1
        sync_session_1 = _create_sync_session(
            db, datetime.combine(day1, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap1 = _create_account_snapshot(db, acct1, sync_session_1)
        _create_holding(db, sync_session_1, acct1, "AAPL", Decimal("10"), Decimal("150"), acct_snap1)

        # acct2 has a sync session only on yesterday
        sync_session_2 = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap2 = _create_account_snapshot(db, acct2, sync_session_2)
        _create_holding(db, sync_session_2, acct2, "GOOG", Decimal("5"), Decimal("2800"), acct_snap2)
        db.commit()

        prices = {
            "AAPL": {day1: Decimal("150"), yesterday: Decimal("155")},
            "GOOG": {yesterday: Decimal("2850")},
        }
        service = _make_mock_service(prices)
        service.backfill(db)

        # Day1: only acct1 (AAPL). Yesterday: acct1 (AAPL) + acct2 (GOOG)
        day1_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.valuation_date == day1)
            .all()
        )
        yesterday_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.valuation_date == yesterday)
            .all()
        )
        assert len(day1_rows) == 1
        assert day1_rows[0].ticker == "AAPL"
        assert len(yesterday_rows) == 2

    def test_failed_account_snapshot_ignored(self, db: Session):
        """Failed account snapshots are not used for valuation."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session, status="failed")
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        service = _make_mock_service({"AAPL": {yesterday: Decimal("155")}})
        service.backfill(db)

        # No valuations since the only account snapshot is failed
        rows = db.query(DailyHoldingValue).all()
        assert len(rows) == 0

    def test_incomplete_sync_session_ignored(self, db: Session):
        """Incomplete sync sessions are not used as start date source."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt, is_complete=False)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        service = _make_mock_service({})
        result = service.backfill(db)

        # No start date found (incomplete sync session)
        assert result.dates_calculated == 0

    def test_market_data_failure_uses_snapshot_price(self, db: Session):
        """If market data service throws, fall back to snapshot prices."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        # Create a service whose market data provider raises
        class FailingProvider:
            @property
            def provider_name(self):
                return "failing"

            def get_price_history(self, symbols, start_date, end_date):
                raise RuntimeError("API down")

        mds = MarketDataService(provider=FailingProvider())
        service = PortfolioValuationService(market_data_service=mds)
        result = service.backfill(db)

        assert len(result.errors) == 1
        assert "Market data fetch failed" in result.errors[0]

        # Still wrote a row using snapshot price as fallback
        row = db.query(DailyHoldingValue).first()
        assert row is not None
        assert row.close_price == Decimal("150")
        assert row.market_value == Decimal("1500.00")

    def test_mixed_holdings_cash_and_equity(self, db: Session):
        """Account with both cash and equity holdings."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        _create_holding(db, sync_session, account, "USD", Decimal("5000"), Decimal("1"), acct_snap)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        service.backfill(db)

        rows = db.query(DailyHoldingValue).order_by(DailyHoldingValue.ticker).all()
        assert len(rows) == 2

        aapl_row = next(r for r in rows if r.ticker == "AAPL")
        usd_row = next(r for r in rows if r.ticker == "USD")

        assert aapl_row.close_price == Decimal("155")
        assert aapl_row.market_value == Decimal("1550.00")
        assert usd_row.close_price == Decimal("1")
        assert usd_row.market_value == Decimal("5000.00")

    def test_cash_prefix_not_fetched_from_market_data(self, db: Session):
        """_CASH: prefixed tickers are excluded from market data lookups."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        _create_holding(db, sync_session, account, "_CASH:USD", Decimal("5000"), Decimal("1"), acct_snap)
        db.commit()

        # Only provide price for AAPL, not for _CASH:USD
        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        result = service.backfill(db)

        # Should only fetch AAPL (1 symbol), not _CASH:USD
        assert result.symbols_fetched == 1

        rows = db.query(DailyHoldingValue).order_by(DailyHoldingValue.ticker).all()
        assert len(rows) == 2

        aapl_row = next(r for r in rows if r.ticker == "AAPL")
        cash_row = next(r for r in rows if r.ticker == "_CASH:USD")

        assert aapl_row.close_price == Decimal("155")
        assert aapl_row.market_value == Decimal("1550.00")
        # _CASH: ticker gets $1.00 price automatically
        assert cash_row.close_price == Decimal("1")
        assert cash_row.market_value == Decimal("5000.00")

    def test_account_snapshot_id_recorded(self, db: Session):
        """Written rows reference the correct account snapshot."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        service.backfill(db)

        row = db.query(DailyHoldingValue).first()
        assert row.account_snapshot_id == acct_snap.id


# ---------------------------------------------------------------------------
# Tests: _calculate_day
# ---------------------------------------------------------------------------
class TestCalculateDay:
    """Tests for the per-day calculation logic."""

    def test_uses_correct_window(self):
        """Selects the latest window on or before the target date."""
        service = PortfolioValuationService()

        timelines = {
            "acct1": [
                SnapshotWindow(
                    effective_date=date(2025, 1, 1),
                    account_snapshot_id="acct_snap1",
                    holdings=[
                        HoldingSummary("AAPL", "sec_aapl", Decimal("10"), Decimal("140")),
                    ],
                ),
                SnapshotWindow(
                    effective_date=date(2025, 1, 10),
                    account_snapshot_id="acct_snap2",
                    holdings=[
                        HoldingSummary("AAPL", "sec_aapl", Decimal("20"), Decimal("150")),
                    ],
                ),
            ],
        }

        price_lookup = {
            "AAPL": {
                date(2025, 1, 5): Decimal("145"),
                date(2025, 1, 10): Decimal("155"),
            },
        }

        # Before transition: uses window 1 (qty=10)
        rows = service._calculate_day(date(2025, 1, 5), timelines, price_lookup)
        assert len(rows) == 1
        assert rows[0].quantity == Decimal("10")
        assert rows[0].close_price == Decimal("145")

        # After transition: uses window 2 (qty=20)
        rows = service._calculate_day(date(2025, 1, 10), timelines, price_lookup)
        assert len(rows) == 1
        assert rows[0].quantity == Decimal("20")
        assert rows[0].close_price == Decimal("155")

    def test_no_window_for_date(self):
        """If no window covers the date, no rows produced."""
        service = PortfolioValuationService()

        timelines = {
            "acct1": [
                SnapshotWindow(
                    effective_date=date(2025, 1, 10),
                    account_snapshot_id="acct_snap1",
                    holdings=[
                        HoldingSummary("AAPL", "sec_aapl", Decimal("10"), Decimal("150")),
                    ],
                ),
            ],
        }

        rows = service._calculate_day(date(2025, 1, 5), timelines, {})
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# Tests: create_daily_values_for_holdings
# ---------------------------------------------------------------------------
class TestCreateDailyValuesForHoldings:
    """Tests for the static helper that creates DailyHoldingValue from holdings."""

    def test_creates_rows(self, db: Session):
        """Creates one DailyHoldingValue per holding."""
        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.now(timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        h1 = _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        h2 = _create_holding(db, sync_session, account, "GOOG", Decimal("5"), Decimal("2800"), acct_snap)
        db.flush()

        today = date.today()
        rows = PortfolioValuationService.create_daily_values_for_holdings(db, [h1, h2], today, account_id=account.id)
        db.flush()

        assert len(rows) == 2
        all_dhv = db.query(DailyHoldingValue).all()
        assert len(all_dhv) == 2

    def test_uses_snapshot_price(self, db: Session):
        """close_price and market_value come from the holding's snapshot values."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        h = _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.flush()

        today = date.today()
        rows = PortfolioValuationService.create_daily_values_for_holdings(db, [h], today, account_id=account.id)
        db.flush()

        assert len(rows) == 1
        dhv = rows[0]
        assert dhv.close_price == Decimal("150")
        assert dhv.market_value == Decimal("1500")
        assert dhv.quantity == Decimal("10")
        assert dhv.ticker == "AAPL"
        assert dhv.valuation_date == today
        assert dhv.account_snapshot_id == acct_snap.id

    def test_upsert_updates_existing(self, db: Session):
        """Calling twice updates existing rows rather than duplicating."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        h = _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.flush()

        today = date.today()
        PortfolioValuationService.create_daily_values_for_holdings(db, [h], today, account_id=account.id)
        db.flush()

        # Update the holding's snapshot values and call again
        h.snapshot_price = Decimal("160")
        h.snapshot_value = Decimal("1600")
        db.flush()

        PortfolioValuationService.create_daily_values_for_holdings(db, [h], today, account_id=account.id)
        db.flush()

        # Should still only have 1 row, updated
        all_dhv = db.query(DailyHoldingValue).all()
        assert len(all_dhv) == 1
        assert all_dhv[0].close_price == Decimal("160")
        assert all_dhv[0].market_value == Decimal("1600")


class TestBackfillUpsert:
    """Tests for backfill updating existing sync-created rows."""

    def test_backfill_skips_when_dhv_current(self, db: Session):
        """Backfill skips when DHV already exists through yesterday."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(
            yesterday, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        # Simulate sync-created DHV row with snapshot price
        security = get_or_create_security(db, "AAPL")
        dhv = DailyHoldingValue(
            valuation_date=yesterday,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("150"),  # snapshot price
            market_value=Decimal("1500"),
        )
        db.add(dhv)
        db.commit()

        # Backfill skips — DHV already current through yesterday
        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        result = service.backfill(db)

        # No market data fetched, existing row untouched
        rows = db.query(DailyHoldingValue).all()
        assert len(rows) == 1
        assert rows[0].close_price == Decimal("150")
        assert result.holdings_written == 0

    def test_backfill_starts_after_last_date(self, db: Session):
        """Backfill starts from the day after the last DHV date."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        snap_dt = datetime.combine(
            day_before, time(12, 0), tzinfo=timezone.utc
        )

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        # Existing DHV for day_before with snapshot price
        security = get_or_create_security(db, "AAPL")
        dhv = DailyHoldingValue(
            valuation_date=day_before,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("150"),
            market_value=Decimal("1500"),
        )
        db.add(dhv)
        db.commit()

        # Backfill with EOD prices
        prices = {
            "AAPL": {
                day_before: Decimal("152"),
                yesterday: Decimal("155"),
            }
        }
        service = _make_mock_service(prices)
        result = service.backfill(db)

        # Starts from yesterday (day after day_before), does NOT reprocess day_before
        assert result.start_date == yesterday
        assert result.dates_calculated == 1
        assert result.holdings_written == 1

        rows = db.query(DailyHoldingValue).order_by(DailyHoldingValue.valuation_date).all()
        assert len(rows) == 2
        assert rows[0].valuation_date == day_before
        assert rows[0].close_price == Decimal("150")  # untouched
        assert rows[1].valuation_date == yesterday
        assert rows[1].close_price == Decimal("155")


class TestSameDayMultiSync:
    """Regression tests for same-day multi-sync deduplication."""

    def test_same_day_resync_updates_not_duplicates(self, db: Session):
        """Two syncs on the same day produce one DHV row per (date, account, security)."""
        account = _create_account(db)

        # First sync
        sync1 = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap1 = _create_account_snapshot(db, account, sync1)
        h1 = _create_holding(db, sync1, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap1)
        db.flush()

        today = date.today()
        PortfolioValuationService.create_daily_values_for_holdings(
            db, [h1], today, account_id=account.id
        )
        db.flush()

        # Second sync (same day, new snapshot, updated price)
        sync2 = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap2 = _create_account_snapshot(db, account, sync2)
        h2 = _create_holding(db, sync2, account, "AAPL", Decimal("10"), Decimal("155"), acct_snap2)
        db.flush()

        PortfolioValuationService.create_daily_values_for_holdings(
            db, [h2], today, account_id=account.id
        )
        db.flush()

        # Only one DHV row should exist
        all_dhv = db.query(DailyHoldingValue).all()
        assert len(all_dhv) == 1
        assert all_dhv[0].close_price == Decimal("155")
        assert all_dhv[0].market_value == Decimal("1550")
        assert all_dhv[0].account_snapshot_id == acct_snap2.id
        assert all_dhv[0].account_id == account.id


# ---------------------------------------------------------------------------
# Tests: _get_start_date (per-account min logic)
# ---------------------------------------------------------------------------
class TestGetStartDate:
    """Tests for the per-account _get_start_date logic."""

    def test_per_account_min(self, db: Session):
        """Start date is the minimum of per-account max DHV dates."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        three_days_ago = yesterday - timedelta(days=2)

        acct1 = _create_account(db, name="Acct1", external_id="ext_1")
        acct2 = _create_account(db, name="Acct2", external_id="ext_2")

        sync_session = _create_sync_session(
            db, datetime.combine(three_days_ago, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap1 = _create_account_snapshot(db, acct1, sync_session)
        acct_snap2 = _create_account_snapshot(db, acct2, sync_session)
        _create_holding(db, sync_session, acct1, "AAPL", Decimal("10"), Decimal("150"), acct_snap1)
        _create_holding(db, sync_session, acct2, "GOOG", Decimal("5"), Decimal("2800"), acct_snap2)

        # Acct1 has DHV through yesterday, acct2 only through day_before
        security_aapl = get_or_create_security(db, "AAPL")
        security_goog = get_or_create_security(db, "GOOG")
        for d in [three_days_ago, day_before, yesterday]:
            db.add(DailyHoldingValue(
                valuation_date=d, account_id=acct1.id,
                account_snapshot_id=acct_snap1.id,
                security_id=security_aapl.id, ticker="AAPL",
                quantity=Decimal("10"), close_price=Decimal("150"),
                market_value=Decimal("1500"),
            ))
        for d in [three_days_ago, day_before]:
            db.add(DailyHoldingValue(
                valuation_date=d, account_id=acct2.id,
                account_snapshot_id=acct_snap2.id,
                security_id=security_goog.id, ticker="GOOG",
                quantity=Decimal("5"), close_price=Decimal("2800"),
                market_value=Decimal("14000"),
            ))
        db.commit()

        service = PortfolioValuationService()
        start = service._get_start_date(db)
        # Acct2's max DHV is day_before, so start = day_before + 1 = yesterday
        assert start == yesterday

    def test_new_account_without_dhv(self, db: Session):
        """Account with no DHV uses first snapshot date."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)

        acct1 = _create_account(db, name="Old", external_id="ext_old")
        acct2 = _create_account(db, name="New", external_id="ext_new")

        sync1 = _create_sync_session(
            db, datetime.combine(day_before, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap1 = _create_account_snapshot(db, acct1, sync1)
        _create_holding(db, sync1, acct1, "AAPL", Decimal("10"), Decimal("150"), acct_snap1)

        # New account's first snapshot is yesterday
        sync2 = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap2 = _create_account_snapshot(db, acct2, sync2)
        _create_holding(db, sync2, acct2, "GOOG", Decimal("5"), Decimal("2800"), acct_snap2)

        # Acct1 has DHV through yesterday
        security_aapl = get_or_create_security(db, "AAPL")
        db.add(DailyHoldingValue(
            valuation_date=yesterday, account_id=acct1.id,
            account_snapshot_id=acct_snap1.id,
            security_id=security_aapl.id, ticker="AAPL",
            quantity=Decimal("10"), close_price=Decimal("150"),
            market_value=Decimal("1500"),
        ))
        db.commit()

        service = PortfolioValuationService()
        start = service._get_start_date(db)
        # New account has no DHV, so falls back to its first snapshot date
        assert start == yesterday

    def test_inactive_account_ignored(self, db: Session):
        """Inactive accounts don't affect start date calculation."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)

        active = _create_account(db, name="Active", external_id="ext_active", is_active=True)
        inactive = _create_account(db, name="Inactive", external_id="ext_inactive", is_active=False)

        sync_session = _create_sync_session(
            db, datetime.combine(day_before, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap_active = _create_account_snapshot(db, active, sync_session)
        acct_snap_inactive = _create_account_snapshot(db, inactive, sync_session)
        _create_holding(db, sync_session, active, "AAPL", Decimal("10"), Decimal("150"), acct_snap_active)
        _create_holding(db, sync_session, inactive, "VTI", Decimal("5"), Decimal("250"), acct_snap_inactive)

        # Only active has DHV
        security_aapl = get_or_create_security(db, "AAPL")
        db.add(DailyHoldingValue(
            valuation_date=yesterday, account_id=active.id,
            account_snapshot_id=acct_snap_active.id,
            security_id=security_aapl.id, ticker="AAPL",
            quantity=Decimal("10"), close_price=Decimal("150"),
            market_value=Decimal("1500"),
        ))
        db.commit()

        service = PortfolioValuationService()
        start = service._get_start_date(db)
        # Active account has DHV through yesterday → start = today (all current)
        assert start == date.today()

    def test_exact_bug_scenario(self, db: Session):
        """Reproduces the exact bug: partial sync leaves permanent holes.

        Day N: Accounts A,B sync (get DHV). Account C doesn't.
        Old logic: start = global max(DHV) = Day N, end = Day N-1 -> skip.
        New logic: start = min(per_account_max) = C's first snapshot -> fills.
        """
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        three_days_ago = yesterday - timedelta(days=2)

        acct_a = _create_account(db, name="A", external_id="ext_a")
        acct_b = _create_account(db, name="B", external_id="ext_b")
        acct_c = _create_account(db, name="C", external_id="ext_c")

        sync_early = _create_sync_session(
            db, datetime.combine(three_days_ago, time(12, 0), tzinfo=timezone.utc)
        )
        snap_a = _create_account_snapshot(db, acct_a, sync_early)
        snap_b = _create_account_snapshot(db, acct_b, sync_early)
        snap_c = _create_account_snapshot(db, acct_c, sync_early)
        _create_holding(db, sync_early, acct_a, "AAPL", Decimal("10"), Decimal("150"), snap_a)
        _create_holding(db, sync_early, acct_b, "GOOG", Decimal("5"), Decimal("2800"), snap_b)
        _create_holding(db, sync_early, acct_c, "VTI", Decimal("20"), Decimal("250"), snap_c)

        security_aapl = get_or_create_security(db, "AAPL")
        security_goog = get_or_create_security(db, "GOOG")

        # Day N (day_before): A and B synced and got DHV, but C did not
        for d in [three_days_ago, day_before]:
            db.add(DailyHoldingValue(
                valuation_date=d, account_id=acct_a.id,
                account_snapshot_id=snap_a.id,
                security_id=security_aapl.id, ticker="AAPL",
                quantity=Decimal("10"), close_price=Decimal("150"),
                market_value=Decimal("1500"),
            ))
            db.add(DailyHoldingValue(
                valuation_date=d, account_id=acct_b.id,
                account_snapshot_id=snap_b.id,
                security_id=security_goog.id, ticker="GOOG",
                quantity=Decimal("5"), close_price=Decimal("2800"),
                market_value=Decimal("14000"),
            ))
        # C has DHV only for three_days_ago, NOT day_before (the gap!)
        security_vti = get_or_create_security(db, "VTI")
        db.add(DailyHoldingValue(
            valuation_date=three_days_ago, account_id=acct_c.id,
            account_snapshot_id=snap_c.id,
            security_id=security_vti.id, ticker="VTI",
            quantity=Decimal("20"), close_price=Decimal("250"),
            market_value=Decimal("5000"),
        ))
        db.commit()

        service = PortfolioValuationService()
        start = service._get_start_date(db)
        # C's max DHV is three_days_ago → start = three_days_ago + 1 = day_before
        assert start == day_before

        # Now run backfill — should fill C's gap at day_before
        prices = {
            "AAPL": {
                three_days_ago: Decimal("150"), day_before: Decimal("152"),
                yesterday: Decimal("155"),
            },
            "GOOG": {
                three_days_ago: Decimal("2800"), day_before: Decimal("2850"),
                yesterday: Decimal("2900"),
            },
            "VTI": {
                three_days_ago: Decimal("250"), day_before: Decimal("252"),
                yesterday: Decimal("255"),
            },
        }
        service = _make_mock_service(prices)
        result = service.backfill(db)

        # C should now have DHV for day_before and yesterday
        c_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.account_id == acct_c.id)
            .order_by(DailyHoldingValue.valuation_date)
            .all()
        )
        c_dates = [r.valuation_date for r in c_rows]
        assert day_before in c_dates
        assert yesterday in c_dates
        assert result.dates_calculated > 0

    def test_no_active_accounts(self, db: Session):
        """Returns None when there are no active accounts."""
        _create_account(db, name="Inactive", external_id="ext_1", is_active=False)
        db.commit()

        service = PortfolioValuationService()
        assert service._get_start_date(db) is None

    def test_no_snapshots(self, db: Session):
        """Returns None when active accounts have no snapshots."""
        _create_account(db, name="Empty", external_id="ext_1")
        db.commit()

        service = PortfolioValuationService()
        assert service._get_start_date(db) is None


# ---------------------------------------------------------------------------
# Tests: diagnose_gaps
# ---------------------------------------------------------------------------
class TestDiagnoseGaps:
    """Tests for the diagnose_gaps method."""

    def test_no_gaps(self, db: Session):
        """Account with complete DHV coverage shows zero gaps."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(day_before, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        security = get_or_create_security(db, "AAPL")
        for d in [day_before, yesterday]:
            db.add(DailyHoldingValue(
                valuation_date=d, account_id=account.id,
                account_snapshot_id=acct_snap.id,
                security_id=security.id, ticker="AAPL",
                quantity=Decimal("10"), close_price=Decimal("150"),
                market_value=Decimal("1500"),
            ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["missing_days"] == 0
        assert gaps[0]["missing_dates"] == []
        assert gaps[0]["partial_days"] == 0
        assert gaps[0]["partial_dates"] == []

    def test_missing_dates_detected(self, db: Session):
        """Account with gaps shows correct missing dates."""
        yesterday = date.today() - timedelta(days=1)
        three_days_ago = yesterday - timedelta(days=2)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(three_days_ago, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        security = get_or_create_security(db, "AAPL")
        # Only has DHV for three_days_ago and yesterday, missing day_before
        for d in [three_days_ago, yesterday]:
            db.add(DailyHoldingValue(
                valuation_date=d, account_id=account.id,
                account_snapshot_id=acct_snap.id,
                security_id=security.id, ticker="AAPL",
                quantity=Decimal("10"), close_price=Decimal("150"),
                market_value=Decimal("1500"),
            ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        day_before = yesterday - timedelta(days=1)
        assert gaps[0]["missing_days"] == 1
        assert day_before.isoformat() in gaps[0]["missing_dates"]

    def test_new_account_no_dhv(self, db: Session):
        """Account with snapshots but no DHV shows all days missing."""
        yesterday = date.today() - timedelta(days=1)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["missing_days"] == 1
        assert gaps[0]["actual_days"] == 0

    def test_partial_gap_detected(self, db: Session):
        """Date with DHV for one holding but not another → partial_days == 1."""
        yesterday = date.today() - timedelta(days=1)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        _create_holding(db, sync_session, account, "GOOG", Decimal("5"), Decimal("100"), acct_snap)

        # Only create DHV for AAPL, not GOOG
        sec_aapl = get_or_create_security(db, "AAPL")
        db.add(DailyHoldingValue(
            valuation_date=yesterday, account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id, ticker="AAPL",
            quantity=Decimal("10"), close_price=Decimal("150"),
            market_value=Decimal("1500"),
        ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["missing_days"] == 0
        assert gaps[0]["partial_days"] == 1
        assert yesterday.isoformat() in gaps[0]["partial_dates"]

    def test_sentinel_not_partial(self, db: Session):
        """Zero-balance sentinel date should not be flagged as partial."""
        yesterday = date.today() - timedelta(days=1)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        # No real holdings — only a zero-balance sentinel

        sentinel_sec = get_or_create_security(db, ZERO_BALANCE_TICKER)
        db.add(DailyHoldingValue(
            valuation_date=yesterday, account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=sentinel_sec.id, ticker=ZERO_BALANCE_TICKER,
            quantity=Decimal("0"), close_price=Decimal("0"),
            market_value=Decimal("0"),
        ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["missing_days"] == 0
        assert gaps[0]["partial_days"] == 0

    def test_multiple_partial_dates(self, db: Session):
        """Two dates each missing a holding → partial_days == 2."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(day_before, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        _create_holding(db, sync_session, account, "GOOG", Decimal("5"), Decimal("100"), acct_snap)

        sec_aapl = get_or_create_security(db, "AAPL")
        sec_goog = get_or_create_security(db, "GOOG")

        # day_before: only AAPL (missing GOOG)
        db.add(DailyHoldingValue(
            valuation_date=day_before, account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id, ticker="AAPL",
            quantity=Decimal("10"), close_price=Decimal("150"),
            market_value=Decimal("1500"),
        ))
        # yesterday: only GOOG (missing AAPL)
        db.add(DailyHoldingValue(
            valuation_date=yesterday, account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_goog.id, ticker="GOOG",
            quantity=Decimal("5"), close_price=Decimal("100"),
            market_value=Decimal("500"),
        ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["missing_days"] == 0
        assert gaps[0]["partial_days"] == 2

    def test_mixed_missing_and_partial(self, db: Session):
        """One date fully missing, another partial."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        two_days_ago = yesterday - timedelta(days=2)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(two_days_ago, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        _create_holding(db, sync_session, account, "GOOG", Decimal("5"), Decimal("100"), acct_snap)

        sec_aapl = get_or_create_security(db, "AAPL")
        sec_goog = get_or_create_security(db, "GOOG")

        # two_days_ago: complete (both AAPL + GOOG)
        for sec, ticker, qty, price, mv in [
            (sec_aapl, "AAPL", "10", "150", "1500"),
            (sec_goog, "GOOG", "5", "100", "500"),
        ]:
            db.add(DailyHoldingValue(
                valuation_date=two_days_ago, account_id=account.id,
                account_snapshot_id=acct_snap.id,
                security_id=sec.id, ticker=ticker,
                quantity=Decimal(qty), close_price=Decimal(price),
                market_value=Decimal(mv),
            ))
        # day_before: NO DHV rows (fully missing)
        # yesterday: only AAPL (partial)
        db.add(DailyHoldingValue(
            valuation_date=yesterday, account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id, ticker="AAPL",
            quantity=Decimal("10"), close_price=Decimal("150"),
            market_value=Decimal("1500"),
        ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["missing_days"] == 1
        assert day_before.isoformat() in gaps[0]["missing_dates"]
        assert gaps[0]["partial_days"] == 1
        assert yesterday.isoformat() in gaps[0]["partial_dates"]

    def test_complete_missing_day_regression(self, db: Session):
        """Regression: completely missing day still reported in missing_days."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(day_before, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        # Only DHV for day_before, not yesterday
        security = get_or_create_security(db, "AAPL")
        db.add(DailyHoldingValue(
            valuation_date=day_before, account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id, ticker="AAPL",
            quantity=Decimal("10"), close_price=Decimal("150"),
            market_value=Decimal("1500"),
        ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["missing_days"] == 1
        assert yesterday.isoformat() in gaps[0]["missing_dates"]
        assert gaps[0]["partial_days"] == 0


# ---------------------------------------------------------------------------
# Tests: full_backfill
# ---------------------------------------------------------------------------
class TestFullBackfill:
    """Tests for the full_backfill method."""

    def test_processes_from_earliest(self, db: Session):
        """Full backfill starts from the earliest snapshot, not latest DHV."""
        yesterday = date.today() - timedelta(days=1)
        three_days_ago = yesterday - timedelta(days=2)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(three_days_ago, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        prices = {
            "AAPL": {
                three_days_ago: Decimal("150"),
                three_days_ago + timedelta(days=1): Decimal("152"),
                yesterday: Decimal("155"),
            },
        }
        service = _make_mock_service(prices)
        result = service.full_backfill(db)

        assert result.start_date == three_days_ago
        assert result.end_date == yesterday
        assert result.dates_calculated == 3

        rows = db.query(DailyHoldingValue).all()
        assert len(rows) == 3

    def test_fills_existing_gaps(self, db: Session):
        """Full backfill fills gaps in existing DHV data."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        three_days_ago = yesterday - timedelta(days=2)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(three_days_ago, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        # Has DHV for three_days_ago and yesterday, gap at day_before
        security = get_or_create_security(db, "AAPL")
        for d in [three_days_ago, yesterday]:
            db.add(DailyHoldingValue(
                valuation_date=d, account_id=account.id,
                account_snapshot_id=acct_snap.id,
                security_id=security.id, ticker="AAPL",
                quantity=Decimal("10"), close_price=Decimal("150"),
                market_value=Decimal("1500"),
            ))
        db.commit()

        prices = {
            "AAPL": {
                three_days_ago: Decimal("150"),
                day_before: Decimal("152"),
                yesterday: Decimal("155"),
            },
        }
        service = _make_mock_service(prices)
        service.full_backfill(db)

        # Gap at day_before should now be filled
        rows = (
            db.query(DailyHoldingValue)
            .order_by(DailyHoldingValue.valuation_date)
            .all()
        )
        dates = [r.valuation_date for r in rows]
        assert day_before in dates
        assert len(rows) == 3

    def test_no_sync_sessions(self, db: Session):
        """No sync sessions -> no-op."""
        service = _make_mock_service({})
        result = service.full_backfill(db)
        assert result.dates_calculated == 0


class TestUtcToLocalDate:
    """Tests for the _utc_to_local_date helper."""

    def test_naive_utc_converted(self):
        """Naive UTC datetime is treated as UTC and converted to local date."""
        # This is a basic sanity check — exact result depends on system timezone
        utc_dt = datetime(2026, 2, 11, 1, 0, 0)  # naive
        result = PortfolioValuationService._utc_to_local_date(utc_dt)
        assert isinstance(result, date)

    def test_aware_utc_converted(self):
        """Timezone-aware UTC datetime is converted correctly."""
        utc_dt = datetime(2026, 2, 11, 1, 0, 0, tzinfo=timezone.utc)
        result = PortfolioValuationService._utc_to_local_date(utc_dt)
        assert isinstance(result, date)

    def test_midnight_utc_same_day_in_utc(self):
        """Midnight UTC should be the same date in UTC and later timezones."""
        utc_dt = datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc)
        result = PortfolioValuationService._utc_to_local_date(utc_dt)
        # In UTC or any timezone behind UTC (Americas), this is Feb 10 or Feb 11
        # In UTC or any timezone ahead of UTC (Asia), this is Feb 11
        # Either way, it should be a valid date
        assert result in (date(2026, 2, 10), date(2026, 2, 11))


class TestTimelineUtcOffset:
    """Regression test: backfill must use local dates, not UTC dates,
    when resolving snapshot timelines.

    The bug: A sync at 5 PM PT on Feb 10 creates SyncSession.timestamp =
    Feb 11 01:00 UTC. The old timeline code used func.date(timestamp) which
    extracted Feb 11 — making the snapshot invisible for Feb 10 backfill.
    The backfill would then use an older snapshot and overwrite
    account_snapshot_id, breaking the dashboard.
    """

    def test_backfill_uses_correct_snapshot_when_utc_date_differs(
        self, db: Session, monkeypatch
    ):
        """Backfill resolves to the correct snapshot even when the UTC date
        of the sync is one day ahead of the local date.
        """
        yesterday = date.today() - timedelta(days=1)
        two_days_ago = yesterday - timedelta(days=1)

        account = _create_account(db)

        # Old sync: 2 days ago (unambiguous — same date in all timezones)
        old_sync = _create_sync_session(
            db, datetime.combine(two_days_ago, time(12, 0), tzinfo=timezone.utc)
        )
        old_snap = _create_account_snapshot(db, account, old_sync)
        _create_holding(db, old_sync, account, "AAPL", Decimal("10"), Decimal("100"), old_snap)

        # New sync: yesterday at 01:00 UTC.
        # In PT (UTC-8), this would be two_days_ago at 5 PM.
        # The key: func.date() would return 'yesterday' but the local date
        # is 'two_days_ago'. We mock _utc_to_local_date to simulate PT.
        new_sync_ts = datetime.combine(yesterday, time(1, 0), tzinfo=timezone.utc)
        new_sync = _create_sync_session(db, new_sync_ts)
        new_snap = _create_account_snapshot(db, account, new_sync)
        _create_holding(db, new_sync, account, "AAPL", Decimal("20"), Decimal("150"), new_snap)
        db.commit()

        # Mock _utc_to_local_date to simulate US/Pacific: UTC 01:00 on 'yesterday'
        # maps to the day before in local time
        def mock_utc_to_local(utc_dt):
            """Simulate PT: subtract 8 hours before extracting date."""
            if utc_dt.tzinfo is None:
                utc_dt = utc_dt.replace(tzinfo=timezone.utc)
            pt = timezone(timedelta(hours=-8))
            return utc_dt.astimezone(pt).date()

        monkeypatch.setattr(
            PortfolioValuationService, "_utc_to_local_date", staticmethod(mock_utc_to_local)
        )

        prices = {
            "AAPL": {
                two_days_ago: Decimal("100"),
            }
        }
        service = _make_mock_service(prices)

        # Backfill for just two_days_ago
        service._run_backfill(db, two_days_ago, two_days_ago)

        # The backfill should resolve to the NEW snapshot (20 shares @ $100)
        # because the new sync's local date is two_days_ago (5 PM PT).
        # If the old UTC-based code ran, it would use the OLD snapshot
        # (10 shares @ $100).
        dhv_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.valuation_date == two_days_ago)
            .all()
        )
        assert len(dhv_rows) == 1
        assert dhv_rows[0].quantity == Decimal("20")
        assert dhv_rows[0].account_snapshot_id == new_snap.id


# ---------------------------------------------------------------------------
# Tests: write_zero_balance_sentinel / delete_zero_balance_sentinel
# ---------------------------------------------------------------------------
class TestZeroBalanceSentinel:
    """Tests for sentinel DHV row helpers."""

    def test_write_creates_sentinel_dhv_and_security(self, db: Session):
        """write_zero_balance_sentinel creates a _ZERO_BALANCE Security and DHV."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        db.commit()

        today = date.today()
        dhv = PortfolioValuationService.write_zero_balance_sentinel(
            db, account.id, acct_snap.id, today
        )
        db.flush()

        assert dhv.ticker == ZERO_BALANCE_TICKER
        assert dhv.market_value == Decimal("0")
        assert dhv.quantity == Decimal("0")
        assert dhv.close_price == Decimal("0")
        assert dhv.account_id == account.id
        assert dhv.valuation_date == today

        # Security should exist
        security = db.query(Security).filter_by(ticker=ZERO_BALANCE_TICKER).first()
        assert security is not None
        assert security.name == "Zero Balance Sentinel"

    def test_write_upserts_idempotent(self, db: Session):
        """Calling write_zero_balance_sentinel twice doesn't create duplicates."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        db.commit()

        today = date.today()
        PortfolioValuationService.write_zero_balance_sentinel(
            db, account.id, acct_snap.id, today
        )
        db.flush()

        # Second call with different snapshot
        sync2 = _create_sync_session(db, datetime.now(timezone.utc))
        snap2 = _create_account_snapshot(db, account, sync2)
        PortfolioValuationService.write_zero_balance_sentinel(
            db, account.id, snap2.id, today
        )
        db.flush()

        rows = db.query(DailyHoldingValue).filter(
            DailyHoldingValue.account_id == account.id,
            DailyHoldingValue.valuation_date == today,
        ).all()
        assert len(rows) == 1
        assert rows[0].account_snapshot_id == snap2.id

    def test_write_deletes_stale_real_dhvs(self, db: Session):
        """write_zero_balance_sentinel deletes real DHV rows for the same account+date."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        h = _create_holding(
            db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap
        )
        db.flush()

        today = date.today()
        PortfolioValuationService.create_daily_values_for_holdings(
            db, [h], today, account_id=account.id
        )
        db.flush()
        assert db.query(DailyHoldingValue).count() == 1

        # Now write sentinel — should delete the AAPL row
        PortfolioValuationService.write_zero_balance_sentinel(
            db, account.id, acct_snap.id, today
        )
        db.flush()

        rows = db.query(DailyHoldingValue).all()
        assert len(rows) == 1
        assert rows[0].ticker == ZERO_BALANCE_TICKER

    def test_delete_removes_sentinel(self, db: Session):
        """delete_zero_balance_sentinel removes the sentinel DHV row."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        db.commit()

        today = date.today()
        PortfolioValuationService.write_zero_balance_sentinel(
            db, account.id, acct_snap.id, today
        )
        db.flush()
        assert db.query(DailyHoldingValue).count() == 1

        PortfolioValuationService.delete_zero_balance_sentinel(
            db, account.id, today
        )
        db.flush()
        assert db.query(DailyHoldingValue).count() == 0

    def test_delete_noop_when_security_missing(self, db: Session):
        """delete_zero_balance_sentinel is a no-op when _ZERO_BALANCE Security doesn't exist."""
        account = _create_account(db)
        db.commit()

        # Should not raise
        PortfolioValuationService.delete_zero_balance_sentinel(
            db, account.id, date.today()
        )


# ---------------------------------------------------------------------------
# Tests: Backfill with zero-holding accounts
# ---------------------------------------------------------------------------
class TestBackfillZeroHoldings:
    """Tests for backfill handling of empty-holdings windows."""

    def test_backfill_empty_holdings_writes_sentinel(self, db: Session):
        """Backfill with an empty-holdings window writes sentinel DHV rows."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        # Create a snapshot with NO holdings (liquidated account)
        _create_account_snapshot(db, account, sync_session)
        db.commit()

        service = _make_mock_service({})
        result = service.backfill(db)

        assert result.dates_calculated == 1
        rows = db.query(DailyHoldingValue).all()
        assert len(rows) == 1
        assert rows[0].ticker == ZERO_BALANCE_TICKER
        assert rows[0].market_value == Decimal("0")
        assert rows[0].account_id == account.id

    def test_backfill_all_empty_accounts_no_early_return(self, db: Session):
        """Backfill doesn't early-return when all accounts have empty holdings."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)

        acct1 = _create_account(db, name="Liq1", external_id="ext_liq1")
        acct2 = _create_account(db, name="Liq2", external_id="ext_liq2")
        sync_session = _create_sync_session(db, snap_dt)
        _create_account_snapshot(db, acct1, sync_session)
        _create_account_snapshot(db, acct2, sync_session)
        db.commit()

        service = _make_mock_service({})
        result = service.backfill(db)

        assert result.dates_calculated == 1
        rows = db.query(DailyHoldingValue).all()
        assert len(rows) == 2
        assert all(r.ticker == ZERO_BALANCE_TICKER for r in rows)

    def test_backfill_transition_real_to_zero(self, db: Session):
        """Backfill transition: account goes from real holdings to zero."""
        yesterday = date.today() - timedelta(days=1)
        day1 = yesterday - timedelta(days=1)

        account = _create_account(db)

        # Day1: has AAPL
        sync1 = _create_sync_session(
            db, datetime.combine(day1, time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _create_account_snapshot(db, account, sync1)
        _create_holding(db, sync1, account, "AAPL", Decimal("10"), Decimal("150"), snap1)

        # Yesterday: liquidated (empty holdings)
        sync2 = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        _create_account_snapshot(db, account, sync2)
        db.commit()

        prices = {
            "AAPL": {
                day1: Decimal("150"),
                yesterday: Decimal("155"),
            }
        }
        service = _make_mock_service(prices)
        service.backfill(db)

        # Day1 should have real AAPL row
        day1_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.valuation_date == day1)
            .all()
        )
        assert len(day1_rows) == 1
        assert day1_rows[0].ticker == "AAPL"

        # Yesterday should have sentinel row, no AAPL
        yesterday_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.valuation_date == yesterday)
            .all()
        )
        assert len(yesterday_rows) == 1
        assert yesterday_rows[0].ticker == ZERO_BALANCE_TICKER
        assert yesterday_rows[0].market_value == Decimal("0")

    def test_backfill_transition_zero_to_real(self, db: Session):
        """Backfill transition: account goes from zero holdings to real."""
        yesterday = date.today() - timedelta(days=1)
        day1 = yesterday - timedelta(days=1)

        account = _create_account(db)

        # Day1: empty (liquidated)
        sync1 = _create_sync_session(
            db, datetime.combine(day1, time(12, 0), tzinfo=timezone.utc)
        )
        _create_account_snapshot(db, account, sync1)

        # Yesterday: acquired AAPL
        sync2 = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _create_account_snapshot(db, account, sync2)
        _create_holding(db, sync2, account, "AAPL", Decimal("10"), Decimal("150"), snap2)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        service.backfill(db)

        # Day1 should have sentinel
        day1_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.valuation_date == day1)
            .all()
        )
        assert len(day1_rows) == 1
        assert day1_rows[0].ticker == ZERO_BALANCE_TICKER

        # Yesterday should have real AAPL row, no sentinel
        yesterday_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.valuation_date == yesterday)
            .all()
        )
        assert len(yesterday_rows) == 1
        assert yesterday_rows[0].ticker == "AAPL"

    def test_backfill_replaces_stale_real_with_sentinel(self, db: Session):
        """Backfill cleans up existing real DHVs when account becomes empty."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)

        # Old sync with holdings
        old_sync = _create_sync_session(
            db, datetime.combine(yesterday - timedelta(days=1), time(12, 0), tzinfo=timezone.utc)
        )
        old_snap = _create_account_snapshot(db, account, old_sync)
        _create_holding(db, old_sync, account, "AAPL", Decimal("10"), Decimal("150"), old_snap)

        # Pre-existing real DHV for yesterday (from prior backfill)
        security = get_or_create_security(db, "AAPL")
        dhv = DailyHoldingValue(
            valuation_date=yesterday,
            account_id=account.id,
            account_snapshot_id=old_snap.id,
            security_id=security.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("150"),
            market_value=Decimal("1500"),
        )
        db.add(dhv)

        # New sync with no holdings (liquidated)
        new_sync = _create_sync_session(db, snap_dt)
        _create_account_snapshot(db, account, new_sync)
        db.commit()

        service = _make_mock_service({})
        service.full_backfill(db)

        # Yesterday should only have sentinel, old AAPL DHV should be deleted
        yesterday_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.valuation_date == yesterday)
            .all()
        )
        assert len(yesterday_rows) == 1
        assert yesterday_rows[0].ticker == ZERO_BALANCE_TICKER

    def test_backfill_replaces_stale_sentinel_with_real(self, db: Session):
        """Backfill cleans up existing sentinel DHVs when account gets holdings."""
        yesterday = date.today() - timedelta(days=1)

        account = _create_account(db)

        # Old sync with no holdings
        old_sync = _create_sync_session(
            db, datetime.combine(yesterday - timedelta(days=1), time(12, 0), tzinfo=timezone.utc)
        )
        old_snap = _create_account_snapshot(db, account, old_sync)

        # Pre-existing sentinel DHV for yesterday
        sentinel_sec = get_or_create_security(db, ZERO_BALANCE_TICKER, "Zero Balance Sentinel")
        sentinel_dhv = DailyHoldingValue(
            valuation_date=yesterday,
            account_id=account.id,
            account_snapshot_id=old_snap.id,
            security_id=sentinel_sec.id,
            ticker=ZERO_BALANCE_TICKER,
            quantity=Decimal("0"),
            close_price=Decimal("0"),
            market_value=Decimal("0"),
        )
        db.add(sentinel_dhv)

        # New sync with real holdings
        snap_dt = datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        new_sync = _create_sync_session(db, snap_dt)
        new_snap = _create_account_snapshot(db, account, new_sync)
        _create_holding(db, new_sync, account, "AAPL", Decimal("10"), Decimal("150"), new_snap)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        service.full_backfill(db)

        # Yesterday should only have real AAPL row, sentinel should be deleted
        yesterday_rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.valuation_date == yesterday)
            .all()
        )
        assert len(yesterday_rows) == 1
        assert yesterday_rows[0].ticker == "AAPL"


# ---------------------------------------------------------------------------
# Tests: _detect_crypto_symbols
# ---------------------------------------------------------------------------
class TestDetectCryptoSymbols:
    """Tests for crypto symbol detection via asset classification."""

    def test_no_crypto_asset_class(self, db: Session):
        """Returns None when no 'Crypto' asset class exists."""
        result = PortfolioValuationService._detect_crypto_symbols(db)
        assert result is None

    def test_crypto_class_exists_no_securities(self, db: Session):
        """Returns None when Crypto class exists but no securities are assigned."""
        crypto_class = AssetClass(name="Crypto", target_percent=Decimal("10"))
        db.add(crypto_class)
        db.flush()

        result = PortfolioValuationService._detect_crypto_symbols(db)
        assert result is None

    def test_crypto_class_with_securities(self, db: Session):
        """Returns set of crypto tickers when securities are classified."""
        crypto_class = AssetClass(name="Crypto", target_percent=Decimal("10"))
        db.add(crypto_class)
        db.flush()

        btc_sec = Security(ticker="BTC", name="Bitcoin", manual_asset_class_id=crypto_class.id)
        eth_sec = Security(ticker="ETH", name="Ethereum", manual_asset_class_id=crypto_class.id)
        db.add(btc_sec)
        db.add(eth_sec)
        db.flush()

        result = PortfolioValuationService._detect_crypto_symbols(db)
        assert result == {"BTC", "ETH"}

    def test_non_crypto_securities_not_included(self, db: Session):
        """Securities in other asset classes are not returned."""
        crypto_class = AssetClass(name="Crypto", target_percent=Decimal("10"))
        equity_class = AssetClass(name="US Equities", target_percent=Decimal("60"))
        db.add(crypto_class)
        db.add(equity_class)
        db.flush()

        btc_sec = Security(ticker="BTC", name="Bitcoin", manual_asset_class_id=crypto_class.id)
        aapl_sec = Security(ticker="AAPL", name="Apple", manual_asset_class_id=equity_class.id)
        db.add(btc_sec)
        db.add(aapl_sec)
        db.flush()

        result = PortfolioValuationService._detect_crypto_symbols(db)
        assert result == {"BTC"}
        assert "AAPL" not in result

    def test_backfill_passes_crypto_symbols_to_market_data(self, db: Session):
        """Backfill detects crypto and routes to market data service correctly."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)

        # Set up crypto asset class and security
        crypto_class = AssetClass(name="Crypto", target_percent=Decimal("10"))
        db.add(crypto_class)
        db.flush()

        btc_sec = Security(ticker="BTC", name="Bitcoin", manual_asset_class_id=crypto_class.id)
        db.add(btc_sec)
        db.flush()

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)

        # Create BTC holding linked to the security
        h = Holding(
            account_snapshot_id=acct_snap.id,
            security_id=btc_sec.id,
            ticker="BTC",
            quantity=Decimal("0.5"),
            snapshot_price=Decimal("42000"),
            snapshot_value=Decimal("21000"),
        )
        db.add(h)
        db.commit()

        # Track what crypto_symbols were passed to get_price_history
        captured_crypto_symbols = []

        class TrackingMarketDataService(MarketDataService):
            def get_price_history(self, symbols, start_date, end_date, crypto_symbols=None):
                captured_crypto_symbols.append(crypto_symbols)
                return {s: [] for s in symbols}

        service = PortfolioValuationService(
            market_data_service=TrackingMarketDataService(),
        )
        service.backfill(db)

        # Verify crypto_symbols was passed
        assert len(captured_crypto_symbols) == 1
        assert captured_crypto_symbols[0] is not None
        assert "BTC" in captured_crypto_symbols[0]
