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
    PRICE_SOURCE_CARRY_FORWARD,
    PRICE_SOURCE_CASH,
    PRICE_SOURCE_CORRECTED,
    PRICE_SOURCE_MARKET,
    PRICE_SOURCE_SNAPSHOT,
    STALE_PRICE_DAYS,
    HoldingSummary,
    PortfolioValuationService,
    PriceWithDate,
    SnapshotWindow,
    ValuationResult,
    build_price_lookup,
    is_cash_equivalent,
)
from tests.fixtures import get_or_create_security
from utils.ticker import SYNTHETIC_PREFIX, ZERO_BALANCE_TICKER


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
        """Trading day prices are mapped correctly with correct price_date."""
        market_data = {
            "AAPL": [
                PriceResult("AAPL", date(2025, 1, 6), Decimal("150"), "mock"),
                PriceResult("AAPL", date(2025, 1, 7), Decimal("152"), "mock"),
            ]
        }
        lookup = build_price_lookup(
            market_data, date(2025, 1, 6), date(2025, 1, 7)
        )
        assert lookup["AAPL"][date(2025, 1, 6)] == PriceWithDate(Decimal("150"), date(2025, 1, 6), PRICE_SOURCE_MARKET)
        assert lookup["AAPL"][date(2025, 1, 7)] == PriceWithDate(Decimal("152"), date(2025, 1, 7), PRICE_SOURCE_MARKET)

    def test_carry_forward_over_weekend(self):
        """Friday's price carries forward through Saturday and Sunday with Friday's price_date."""
        market_data = {
            "AAPL": [
                PriceResult("AAPL", date(2025, 1, 3), Decimal("150"), "mock"),  # Fri
                PriceResult("AAPL", date(2025, 1, 6), Decimal("155"), "mock"),  # Mon
            ]
        }
        lookup = build_price_lookup(
            market_data, date(2025, 1, 3), date(2025, 1, 6)
        )
        assert lookup["AAPL"][date(2025, 1, 3)].price == Decimal("150")
        assert lookup["AAPL"][date(2025, 1, 3)].price_date == date(2025, 1, 3)
        assert lookup["AAPL"][date(2025, 1, 4)].price == Decimal("150")  # Sat
        assert lookup["AAPL"][date(2025, 1, 4)].price_date == date(2025, 1, 3)  # Still Friday
        assert lookup["AAPL"][date(2025, 1, 5)].price == Decimal("150")  # Sun
        assert lookup["AAPL"][date(2025, 1, 5)].price_date == date(2025, 1, 3)  # Still Friday
        assert lookup["AAPL"][date(2025, 1, 6)].price == Decimal("155")
        assert lookup["AAPL"][date(2025, 1, 6)].price_date == date(2025, 1, 6)

    def test_carry_forward_over_holiday(self):
        """Holiday gap is filled with the prior close and its price_date."""
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
        assert lookup["AAPL"][date(2025, 1, 3)].price == Decimal("148")
        assert lookup["AAPL"][date(2025, 1, 3)].price_date == date(2025, 1, 2)
        assert lookup["AAPL"][date(2025, 1, 4)].price == Decimal("148")
        assert lookup["AAPL"][date(2025, 1, 4)].price_date == date(2025, 1, 2)
        assert lookup["AAPL"][date(2025, 1, 5)].price == Decimal("148")
        assert lookup["AAPL"][date(2025, 1, 5)].price_date == date(2025, 1, 2)

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
        assert lookup["AAPL"][date(2025, 1, 8)].price == Decimal("155")
        assert lookup["AAPL"][date(2025, 1, 9)].price == Decimal("155")
        assert lookup["AAPL"][date(2025, 1, 9)].price_date == date(2025, 1, 8)  # carry-forward

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
        assert lookup["AAPL"][date(2025, 1, 6)].price == Decimal("150")
        assert lookup["GOOG"][date(2025, 1, 6)].price == Decimal("2800")

    def test_extended_stale_carry_forward(self):
        """Price_date stays at last real trading day even over 30+ day gap."""
        market_data = {
            "DELIST": [
                PriceResult("DELIST", date(2025, 1, 6), Decimal("50"), "mock"),
                # No more prices — stock delisted
            ]
        }
        lookup = build_price_lookup(
            market_data, date(2025, 1, 6), date(2025, 2, 10)
        )
        # Day 1 has the actual price date
        assert lookup["DELIST"][date(2025, 1, 6)].price_date == date(2025, 1, 6)
        # 35 days later, still carries forward with the original price_date
        assert lookup["DELIST"][date(2025, 2, 10)].price == Decimal("50")
        assert lookup["DELIST"][date(2025, 2, 10)].price_date == date(2025, 1, 6)


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
                date(2025, 1, 5): PriceWithDate(Decimal("145"), date(2025, 1, 5), PRICE_SOURCE_MARKET),
                date(2025, 1, 10): PriceWithDate(Decimal("155"), date(2025, 1, 10), PRICE_SOURCE_MARKET),
            },
        }

        # Before transition: uses window 1 (qty=10)
        rows = service._calculate_day(date(2025, 1, 5), timelines, price_lookup)
        assert len(rows) == 1
        assert rows[0].quantity == Decimal("10")
        assert rows[0].close_price == Decimal("145")
        assert rows[0].price_date == date(2025, 1, 5)

        # After transition: uses window 2 (qty=20)
        rows = service._calculate_day(date(2025, 1, 10), timelines, price_lookup)
        assert len(rows) == 1
        assert rows[0].quantity == Decimal("20")
        assert rows[0].close_price == Decimal("155")
        assert rows[0].price_date == date(2025, 1, 10)

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
        # Retrospective validation corrects legacy NULL-source row with fresh market data
        assert rows[0].close_price == Decimal("152")
        assert rows[0].price_source == PRICE_SOURCE_CORRECTED
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


# ---------------------------------------------------------------------------
# Tests: _get_price_for_holding price_date behaviour
# ---------------------------------------------------------------------------
class TestGetPriceForHoldingPriceDate:
    """Tests that _get_price_for_holding returns correct PriceWithDate."""

    def test_cash_equivalent_uses_target_date(self):
        """Cash equivalents always return price_date == target_date."""
        result = PortfolioValuationService._get_price_for_holding(
            {}, "USD", date(2025, 6, 15), Decimal("1"),
        )
        assert result == PriceWithDate(Decimal("1"), date(2025, 6, 15), PRICE_SOURCE_CASH)

    def test_market_price_uses_lookup_price_date(self):
        """When market price is available, price_date comes from lookup."""
        lookup = {
            "AAPL": {
                # Weekend carry-forward: Monday lookup has Friday's price_date
                date(2025, 1, 6): PriceWithDate(Decimal("155"), date(2025, 1, 3), PRICE_SOURCE_CARRY_FORWARD),
            },
        }
        result = PortfolioValuationService._get_price_for_holding(
            lookup, "AAPL", date(2025, 1, 6), Decimal("150"),
        )
        assert result.price == Decimal("155")
        assert result.price_date == date(2025, 1, 3)  # Friday, not Monday
        assert result.source == PRICE_SOURCE_CARRY_FORWARD

    def test_snapshot_fallback_uses_effective_date(self):
        """When falling back to snapshot price, price_date == snapshot_effective_date."""
        result = PortfolioValuationService._get_price_for_holding(
            {}, "PRIVCO", date(2025, 6, 15), Decimal("25.50"),
            snapshot_effective_date=date(2025, 6, 10),
        )
        assert result.price == Decimal("25.50")
        assert result.price_date == date(2025, 6, 10)
        assert result.source == PRICE_SOURCE_SNAPSHOT

    def test_snapshot_fallback_no_effective_date(self):
        """Without snapshot_effective_date, fallback uses target_date."""
        result = PortfolioValuationService._get_price_for_holding(
            {}, "PRIVCO", date(2025, 6, 15), Decimal("25.50"),
        )
        assert result.price == Decimal("25.50")
        assert result.price_date == date(2025, 6, 15)
        assert result.source == PRICE_SOURCE_SNAPSHOT


# ---------------------------------------------------------------------------
# Tests: price_date persisted on DHV rows
# ---------------------------------------------------------------------------
class TestPriceDatePersistence:
    """Tests that price_date is correctly persisted on DHV rows."""

    def test_backfill_sets_price_date(self, db: Session):
        """Backfill writes price_date on each DHV row."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        service.backfill(db)

        row = db.query(DailyHoldingValue).first()
        assert row is not None
        assert row.price_date == yesterday

    def test_backfill_carry_forward_price_date(self, db: Session):
        """When price is carried forward, price_date reflects the actual trading day."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        snap_dt = datetime.combine(day_before, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        # Only provide price for day_before, not yesterday (carry-forward)
        prices = {"AAPL": {day_before: Decimal("150")}}
        service = _make_mock_service(prices)
        service.backfill(db)

        rows = (
            db.query(DailyHoldingValue)
            .order_by(DailyHoldingValue.valuation_date)
            .all()
        )
        assert len(rows) == 2
        # Day before: actual price date
        assert rows[0].valuation_date == day_before
        assert rows[0].price_date == day_before
        # Yesterday: carried forward from day_before
        assert rows[1].valuation_date == yesterday
        assert rows[1].price_date == day_before

    def test_cash_price_date_is_valuation_date(self, db: Session):
        """Cash equivalents get price_date == valuation_date (always fresh)."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "USD", Decimal("5000"), Decimal("1"), acct_snap)
        db.commit()

        service = _make_mock_service({})
        service.backfill(db)

        row = db.query(DailyHoldingValue).first()
        assert row is not None
        assert row.price_date == yesterday

    def test_create_daily_values_sets_price_date(self, db: Session):
        """create_daily_values_for_holdings sets price_date = valuation_date."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        h = _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.flush()

        today = date.today()
        rows = PortfolioValuationService.create_daily_values_for_holdings(
            db, [h], today, account_id=account.id
        )
        db.flush()

        assert len(rows) == 1
        assert rows[0].price_date == today

    def test_sentinel_price_date_is_valuation_date(self, db: Session):
        """Zero-balance sentinel rows get price_date == valuation_date."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        db.commit()

        today = date.today()
        dhv = PortfolioValuationService.write_zero_balance_sentinel(
            db, account.id, acct_snap.id, today
        )
        db.flush()

        assert dhv.price_date == today

    def test_upsert_updates_price_date(self, db: Session):
        """Full backfill upsert updates price_date on existing rows."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        # Pre-existing DHV row without price_date
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
            price_date=None,
        )
        db.add(dhv)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        service.full_backfill(db)

        row = db.query(DailyHoldingValue).first()
        assert row is not None
        assert row.price_date == yesterday
        assert row.close_price == Decimal("155")


# ---------------------------------------------------------------------------
# Tests: diagnose_gaps stale price detection
# ---------------------------------------------------------------------------
class TestDiagnoseGapsStalePrice:
    """Tests for stale price detection in diagnose_gaps."""

    def test_stale_price_flagged(self, db: Session):
        """Holdings with price_date > STALE_PRICE_DAYS behind are flagged."""
        yesterday = date.today() - timedelta(days=1)
        old_price_date = yesterday - timedelta(days=STALE_PRICE_DAYS + 5)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "DELIST", Decimal("100"), Decimal("50"), acct_snap)

        security = get_or_create_security(db, "DELIST")
        db.add(DailyHoldingValue(
            valuation_date=yesterday,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id,
            ticker="DELIST",
            quantity=Decimal("100"),
            close_price=Decimal("50"),
            market_value=Decimal("5000"),
            price_date=old_price_date,
        ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["stale_price_count"] == 1
        assert len(gaps[0]["stale_prices"]) == 1
        stale = gaps[0]["stale_prices"][0]
        assert stale["ticker"] == "DELIST"
        assert stale["age_days"] == STALE_PRICE_DAYS + 5

    def test_weekend_not_flagged(self, db: Session):
        """Weekend carry-forward (2 days) is NOT flagged as stale."""
        yesterday = date.today() - timedelta(days=1)
        recent_price_date = yesterday - timedelta(days=2)  # 2-day gap

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        security = get_or_create_security(db, "AAPL")
        db.add(DailyHoldingValue(
            valuation_date=yesterday,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("150"),
            market_value=Decimal("1500"),
            price_date=recent_price_date,
        ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["stale_price_count"] == 0

    def test_null_price_date_skipped(self, db: Session):
        """Rows with price_date=NULL (pre-migration) are not flagged."""
        yesterday = date.today() - timedelta(days=1)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        security = get_or_create_security(db, "AAPL")
        db.add(DailyHoldingValue(
            valuation_date=yesterday,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("150"),
            market_value=Decimal("1500"),
            price_date=None,
        ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["stale_price_count"] == 0

    def test_mixed_stale_and_fresh(self, db: Session):
        """Only stale holdings are flagged; fresh ones are not."""
        yesterday = date.today() - timedelta(days=1)
        old_date = yesterday - timedelta(days=30)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        _create_holding(db, sync_session, account, "DELIST", Decimal("100"), Decimal("50"), acct_snap)

        sec_aapl = get_or_create_security(db, "AAPL")
        sec_delist = get_or_create_security(db, "DELIST")

        db.add(DailyHoldingValue(
            valuation_date=yesterday,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("155"),
            market_value=Decimal("1550"),
            price_date=yesterday,
        ))
        db.add(DailyHoldingValue(
            valuation_date=yesterday,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_delist.id,
            ticker="DELIST",
            quantity=Decimal("100"),
            close_price=Decimal("50"),
            market_value=Decimal("5000"),
            price_date=old_date,
        ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["stale_price_count"] == 1
        assert gaps[0]["stale_prices"][0]["ticker"] == "DELIST"

    def test_synthetic_ticker_not_flagged(self, db: Session):
        """Synthetic tickers (non-tradable holdings) are never flagged as stale."""
        yesterday = date.today() - timedelta(days=1)
        old_date = yesterday - timedelta(days=60)

        account = _create_account(db)
        sync_session = _create_sync_session(
            db, datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)
        )
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "_SYN:abc123def456", Decimal("1"), Decimal("500000"), acct_snap)

        security = get_or_create_security(db, "_SYN:abc123def456", "Primary Residence")
        db.add(DailyHoldingValue(
            valuation_date=yesterday,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id,
            ticker="_SYN:abc123def456",
            quantity=Decimal("1"),
            close_price=Decimal("500000"),
            market_value=Decimal("500000"),
            price_date=old_date,
        ))
        db.commit()

        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)
        assert len(gaps) == 1
        assert gaps[0]["stale_price_count"] == 0


# ---------------------------------------------------------------------------
# Tests: Price Source Tracking
# ---------------------------------------------------------------------------
class TestPriceSourceTracking:
    """Tests for price source field on PriceWithDate and DHV rows."""

    def test_build_price_lookup_tags_market_on_trading_day(self):
        """Prices on actual trading days are tagged as 'market'."""
        market_data = {
            "AAPL": [
                PriceResult("AAPL", date(2025, 1, 6), Decimal("150"), "mock"),
            ]
        }
        lookup = build_price_lookup(market_data, date(2025, 1, 6), date(2025, 1, 6))
        assert lookup["AAPL"][date(2025, 1, 6)].source == PRICE_SOURCE_MARKET

    def test_build_price_lookup_tags_carry_forward_on_weekend(self):
        """Weekend carry-forward prices are tagged as 'carry_forward'."""
        market_data = {
            "AAPL": [
                PriceResult("AAPL", date(2025, 1, 3), Decimal("150"), "mock"),  # Fri
            ]
        }
        lookup = build_price_lookup(market_data, date(2025, 1, 3), date(2025, 1, 5))
        assert lookup["AAPL"][date(2025, 1, 3)].source == PRICE_SOURCE_MARKET
        assert lookup["AAPL"][date(2025, 1, 4)].source == PRICE_SOURCE_CARRY_FORWARD  # Sat
        assert lookup["AAPL"][date(2025, 1, 5)].source == PRICE_SOURCE_CARRY_FORWARD  # Sun

    def test_cash_holding_gets_cash_source(self):
        """Cash equivalents return PRICE_SOURCE_CASH."""
        result = PortfolioValuationService._get_price_for_holding(
            {}, "USD", date(2025, 6, 15), Decimal("1"),
        )
        assert result.source == PRICE_SOURCE_CASH

    def test_snapshot_fallback_gets_snapshot_source(self):
        """When no market data exists, fallback returns PRICE_SOURCE_SNAPSHOT."""
        result = PortfolioValuationService._get_price_for_holding(
            {}, "PRIVCO", date(2025, 6, 15), Decimal("25.50"),
        )
        assert result.source == PRICE_SOURCE_SNAPSHOT

    def test_backfill_writes_price_source_to_dhv(self, db: Session):
        """Backfill writes price_source on each DHV row."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        service.backfill(db)

        row = db.query(DailyHoldingValue).first()
        assert row is not None
        assert row.price_source == PRICE_SOURCE_MARKET

    def test_sentinel_gets_cash_source(self, db: Session):
        """Zero-balance sentinel rows get price_source == PRICE_SOURCE_CASH."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        db.commit()

        today = date.today()
        dhv = PortfolioValuationService.write_zero_balance_sentinel(
            db, account.id, acct_snap.id, today
        )
        db.flush()

        assert dhv.price_source == PRICE_SOURCE_CASH

    def test_sync_creates_snapshot_source(self, db: Session):
        """create_daily_values_for_holdings sets price_source."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        h = _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.flush()

        today = date.today()
        rows = PortfolioValuationService.create_daily_values_for_holdings(
            db, [h], today, account_id=account.id
        )
        db.flush()

        assert len(rows) == 1
        assert rows[0].price_source == PRICE_SOURCE_SNAPSHOT

    def test_sync_creates_cash_source_for_cash_holding(self, db: Session):
        """create_daily_values_for_holdings sets CASH source for cash tickers."""
        account = _create_account(db)
        sync_session = _create_sync_session(db, datetime.now(timezone.utc))
        acct_snap = _create_account_snapshot(db, account, sync_session)
        h = _create_holding(db, sync_session, account, "USD", Decimal("5000"), Decimal("1"), acct_snap)
        db.flush()

        today = date.today()
        rows = PortfolioValuationService.create_daily_values_for_holdings(
            db, [h], today, account_id=account.id
        )
        db.flush()

        assert len(rows) == 1
        assert rows[0].price_source == PRICE_SOURCE_CASH


# ---------------------------------------------------------------------------
# Tests: _load_prior_closes
# ---------------------------------------------------------------------------
class TestLoadPriorCloses:
    """Direct unit tests for _load_prior_closes static method."""

    def test_returns_closes_for_prior_day(self, db: Session):
        """Returns close prices from the day before start_date."""
        account = _create_account(db, "Acct")
        ts = datetime(2025, 1, 6, 12, 0, tzinfo=timezone.utc)
        sync = _create_sync_session(db, ts)
        snap = _create_account_snapshot(db, account, sync)
        security = get_or_create_security(db, "AAPL")
        db.add(DailyHoldingValue(
            valuation_date=date(2025, 1, 5),
            account_id=account.id,
            account_snapshot_id=snap.id,
            security_id=security.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("150"),
            market_value=Decimal("1500"),
        ))
        db.commit()

        result = PortfolioValuationService._load_prior_closes(
            db, date(2025, 1, 6), [account.id]
        )
        assert result == {(account.id, "AAPL"): Decimal("150")}

    def test_returns_empty_when_no_prior_data(self, db: Session):
        """Returns empty dict when no DHV rows exist for the prior day."""
        account = _create_account(db, "Acct")
        result = PortfolioValuationService._load_prior_closes(
            db, date(2025, 1, 6), [account.id]
        )
        assert result == {}

    def test_ignores_other_dates(self, db: Session):
        """Only returns rows from exactly start_date - 1, not other dates."""
        account = _create_account(db, "Acct")
        ts = datetime(2025, 1, 6, 12, 0, tzinfo=timezone.utc)
        sync = _create_sync_session(db, ts)
        snap = _create_account_snapshot(db, account, sync)
        security = get_or_create_security(db, "AAPL")
        # Row for Jan 3 (two days before start)
        db.add(DailyHoldingValue(
            valuation_date=date(2025, 1, 3),
            account_id=account.id,
            account_snapshot_id=snap.id,
            security_id=security.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("140"),
            market_value=Decimal("1400"),
        ))
        db.commit()

        result = PortfolioValuationService._load_prior_closes(
            db, date(2025, 1, 5), [account.id]
        )
        # Jan 4 has no data, so nothing returned
        assert result == {}

    def test_multiple_holdings_multiple_accounts(self, db: Session):
        """Returns entries for all holdings across all specified accounts."""
        acct1 = _create_account(db, "Acct1", external_id="ext1")
        acct2 = _create_account(db, "Acct2", external_id="ext2")
        ts = datetime(2025, 1, 6, 12, 0, tzinfo=timezone.utc)
        sync = _create_sync_session(db, ts)
        snap1 = _create_account_snapshot(db, acct1, sync)
        snap2 = _create_account_snapshot(db, acct2, sync)
        sec_aapl = get_or_create_security(db, "AAPL")
        sec_goog = get_or_create_security(db, "GOOG")

        for acct, snap, ticker, sec, price in [
            (acct1, snap1, "AAPL", sec_aapl, "150"),
            (acct1, snap1, "GOOG", sec_goog, "2800"),
            (acct2, snap2, "AAPL", sec_aapl, "150"),
        ]:
            db.add(DailyHoldingValue(
                valuation_date=date(2025, 1, 5),
                account_id=acct.id,
                account_snapshot_id=snap.id,
                security_id=sec.id,
                ticker=ticker,
                quantity=Decimal("1"),
                close_price=Decimal(price),
                market_value=Decimal(price),
            ))
        db.commit()

        result = PortfolioValuationService._load_prior_closes(
            db, date(2025, 1, 6), [acct1.id, acct2.id]
        )
        assert len(result) == 3
        assert result[(acct1.id, "AAPL")] == Decimal("150")
        assert result[(acct1.id, "GOOG")] == Decimal("2800")
        assert result[(acct2.id, "AAPL")] == Decimal("150")

    def test_ignores_unspecified_accounts(self, db: Session):
        """Only returns rows for the account IDs passed in."""
        acct1 = _create_account(db, "Acct1", external_id="ext1")
        acct2 = _create_account(db, "Acct2", external_id="ext2")
        ts = datetime(2025, 1, 6, 12, 0, tzinfo=timezone.utc)
        sync = _create_sync_session(db, ts)
        snap1 = _create_account_snapshot(db, acct1, sync)
        snap2 = _create_account_snapshot(db, acct2, sync)
        security = get_or_create_security(db, "AAPL")

        for acct, snap in [(acct1, snap1), (acct2, snap2)]:
            db.add(DailyHoldingValue(
                valuation_date=date(2025, 1, 5),
                account_id=acct.id,
                account_snapshot_id=snap.id,
                security_id=security.id,
                ticker="AAPL",
                quantity=Decimal("1"),
                close_price=Decimal("150"),
                market_value=Decimal("150"),
            ))
        db.commit()

        # Only ask for acct1
        result = PortfolioValuationService._load_prior_closes(
            db, date(2025, 1, 6), [acct1.id]
        )
        assert len(result) == 1
        assert (acct1.id, "AAPL") in result
        assert (acct2.id, "AAPL") not in result


# ---------------------------------------------------------------------------
# Tests: Price Guards
# ---------------------------------------------------------------------------
class TestPriceGuards:
    """Tests for the _validate_price static method."""

    def test_zero_price_rejected(self):
        """Zero price is rejected, falls back to snapshot."""
        price_info = PriceWithDate(Decimal("0"), date(2025, 1, 6), PRICE_SOURCE_MARKET)
        result = PortfolioValuationService._validate_price(
            price_info, "AAPL", date(2025, 1, 6),
            Decimal("150"), snapshot_effective_date=date(2025, 1, 5),
        )
        assert result.price == Decimal("150")
        assert result.source == PRICE_SOURCE_SNAPSHOT

    def test_negative_price_rejected(self):
        """Negative price is rejected, falls back to snapshot."""
        price_info = PriceWithDate(Decimal("-5"), date(2025, 1, 6), PRICE_SOURCE_MARKET)
        result = PortfolioValuationService._validate_price(
            price_info, "AAPL", date(2025, 1, 6),
            Decimal("150"), snapshot_effective_date=date(2025, 1, 5),
        )
        assert result.price == Decimal("150")
        assert result.source == PRICE_SOURCE_SNAPSHOT

    def test_normal_price_accepted(self):
        """Normal price within band passes through unchanged."""
        price_info = PriceWithDate(Decimal("155"), date(2025, 1, 6), PRICE_SOURCE_MARKET)
        result = PortfolioValuationService._validate_price(
            price_info, "AAPL", date(2025, 1, 6),
            Decimal("150"), prior_close=Decimal("150"),
        )
        assert result.price == Decimal("155")
        assert result.source == PRICE_SOURCE_MARKET

    def test_equity_spike_rejected(self):
        """100x equity spike is rejected."""
        price_info = PriceWithDate(Decimal("15000"), date(2025, 1, 6), PRICE_SOURCE_MARKET)
        result = PortfolioValuationService._validate_price(
            price_info, "AAPL", date(2025, 1, 6),
            Decimal("150"), prior_close=Decimal("150"),
        )
        assert result.price == Decimal("150")
        assert result.source == PRICE_SOURCE_SNAPSHOT

    def test_equity_crash_rejected(self):
        """1/100x equity crash is rejected."""
        price_info = PriceWithDate(Decimal("1.50"), date(2025, 1, 6), PRICE_SOURCE_MARKET)
        result = PortfolioValuationService._validate_price(
            price_info, "AAPL", date(2025, 1, 6),
            Decimal("150"),
            snapshot_effective_date=date(2025, 1, 5),
            prior_close=Decimal("150"),
        )
        assert result.price == Decimal("150")
        assert result.source == PRICE_SOURCE_SNAPSHOT

    def test_crypto_wider_band(self):
        """Crypto uses wider band — 50x is accepted (within 100x band)."""
        price_info = PriceWithDate(Decimal("2100000"), date(2025, 1, 6), PRICE_SOURCE_MARKET)
        result = PortfolioValuationService._validate_price(
            price_info, "BTC", date(2025, 1, 6),
            Decimal("42000"), prior_close=Decimal("42000"), is_crypto=True,
        )
        assert result.price == Decimal("2100000")  # 50x, within crypto band

    def test_no_prior_close_skips_ratio_check(self):
        """Without prior_close, ratio check is skipped."""
        price_info = PriceWithDate(Decimal("15000"), date(2025, 1, 6), PRICE_SOURCE_MARKET)
        result = PortfolioValuationService._validate_price(
            price_info, "AAPL", date(2025, 1, 6),
            Decimal("150"),
        )
        # No prior close → ratio check skipped → price accepted
        assert result.price == Decimal("15000")

    def test_prior_close_zero_skips_ratio_check(self):
        """Zero prior_close skips ratio check."""
        price_info = PriceWithDate(Decimal("155"), date(2025, 1, 6), PRICE_SOURCE_MARKET)
        result = PortfolioValuationService._validate_price(
            price_info, "AAPL", date(2025, 1, 6),
            Decimal("150"), prior_close=Decimal("0"),
        )
        assert result.price == Decimal("155")

    def test_backfill_progressive_prior_close_update(self, db: Session):
        """Multi-day backfill uses progressive prior close chaining."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        snap_dt = datetime.combine(day_before, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        prices = {
            "AAPL": {
                day_before: Decimal("155"),
                yesterday: Decimal("160"),
            }
        }
        service = _make_mock_service(prices)
        result = service.backfill(db)

        assert result.dates_calculated == 2
        rows = (
            db.query(DailyHoldingValue)
            .order_by(DailyHoldingValue.valuation_date)
            .all()
        )
        assert len(rows) == 2
        assert rows[0].close_price == Decimal("155")
        assert rows[1].close_price == Decimal("160")

    def test_price_guard_logs_warning(self, db: Session, caplog):
        """Price guard rejection logs a warning."""
        import logging
        price_info = PriceWithDate(Decimal("0"), date(2025, 1, 6), PRICE_SOURCE_MARKET)
        with caplog.at_level(logging.WARNING):
            PortfolioValuationService._validate_price(
                price_info, "AAPL", date(2025, 1, 6), Decimal("150"),
            )
        assert "Price guard" in caplog.text
        assert "non-positive" in caplog.text


# ---------------------------------------------------------------------------
# Tests: Retrospective Validation
# ---------------------------------------------------------------------------
class TestRetrospectiveValidation:
    """Tests for the _retrospective_validate method."""

    def _setup_dhv_with_source(
        self, db: Session, account, acct_snap, ticker, val_date,
        close_price, market_value, price_source=None, price_date=None,
    ) -> DailyHoldingValue:
        """Helper to create a DHV row with a specific price_source."""
        security = get_or_create_security(db, ticker)
        dhv = DailyHoldingValue(
            valuation_date=val_date,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id,
            ticker=ticker,
            quantity=Decimal("10"),
            close_price=close_price,
            market_value=market_value,
            price_date=price_date or val_date,
            price_source=price_source,
        )
        db.add(dhv)
        return dhv

    def test_corrects_snapshot_fallback_with_market_data(self, db: Session):
        """Snapshot-sourced DHV rows are corrected when market data becomes available."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        self._setup_dhv_with_source(
            db, account, acct_snap, "AAPL", retro_date,
            Decimal("150"), Decimal("1500"), PRICE_SOURCE_SNAPSHOT,
        )
        db.commit()

        # Market data now shows the real price
        market_data = {
            "AAPL": [
                PriceResult("AAPL", retro_date, Decimal("155"), "mock"),
            ]
        }
        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, market_data, [account.id], None, result,
        )
        db.flush()

        dhv = db.query(DailyHoldingValue).first()
        assert dhv.close_price == Decimal("155")
        assert dhv.price_source == PRICE_SOURCE_CORRECTED
        assert result.corrections == 1

    def test_corrects_carry_forward_with_market_data(self, db: Session):
        """Carry-forward DHV rows are corrected when market data becomes available."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        self._setup_dhv_with_source(
            db, account, acct_snap, "AAPL", retro_date,
            Decimal("148"), Decimal("1480"), PRICE_SOURCE_CARRY_FORWARD,
        )
        db.commit()

        market_data = {
            "AAPL": [
                PriceResult("AAPL", retro_date, Decimal("155"), "mock"),
            ]
        }
        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, market_data, [account.id], None, result,
        )

        dhv = db.query(DailyHoldingValue).first()
        assert dhv.close_price == Decimal("155")
        assert dhv.price_source == PRICE_SOURCE_CORRECTED
        assert result.corrections == 1

    def test_corrects_null_price_source_as_legacy(self, db: Session):
        """NULL price_source (legacy rows) are always corrected."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        self._setup_dhv_with_source(
            db, account, acct_snap, "AAPL", retro_date,
            Decimal("150"), Decimal("1500"), None,  # legacy NULL
        )
        db.commit()

        market_data = {
            "AAPL": [
                PriceResult("AAPL", retro_date, Decimal("155"), "mock"),
            ]
        }
        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, market_data, [account.id], None, result,
        )

        dhv = db.query(DailyHoldingValue).first()
        assert dhv.close_price == Decimal("155")
        assert dhv.price_source == PRICE_SOURCE_CORRECTED

    def test_corrects_market_price_beyond_threshold(self, db: Session):
        """Market-sourced DHV rows are corrected when deviation exceeds threshold."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        # Stored market price differs by > 1% from fresh
        self._setup_dhv_with_source(
            db, account, acct_snap, "AAPL", retro_date,
            Decimal("150"), Decimal("1500"), PRICE_SOURCE_MARKET,
        )
        db.commit()

        market_data = {
            "AAPL": [
                PriceResult("AAPL", retro_date, Decimal("155"), "mock"),  # 3.3% deviation
            ]
        }
        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, market_data, [account.id], None, result,
        )

        dhv = db.query(DailyHoldingValue).first()
        assert dhv.close_price == Decimal("155")
        assert dhv.price_source == PRICE_SOURCE_CORRECTED
        assert result.corrections == 1

    def test_skips_market_price_within_threshold(self, db: Session):
        """Market-sourced DHV rows within threshold are not corrected."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        # Stored market price is very close to fresh (0.1% deviation)
        self._setup_dhv_with_source(
            db, account, acct_snap, "AAPL", retro_date,
            Decimal("150"), Decimal("1500"), PRICE_SOURCE_MARKET,
        )
        db.commit()

        market_data = {
            "AAPL": [
                PriceResult("AAPL", retro_date, Decimal("150.10"), "mock"),  # 0.07%
            ]
        }
        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, market_data, [account.id], None, result,
        )

        dhv = db.query(DailyHoldingValue).first()
        assert dhv.close_price == Decimal("150")  # unchanged
        assert dhv.price_source == PRICE_SOURCE_MARKET
        assert result.corrections == 0

    def test_crypto_uses_wider_threshold(self, db: Session):
        """Crypto uses 5% threshold — 3% deviation is not corrected."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)

        crypto_class = AssetClass(name="Crypto", target_percent=Decimal("10"))
        db.add(crypto_class)
        db.flush()
        btc_sec = Security(ticker="BTC", name="Bitcoin", manual_asset_class_id=crypto_class.id)
        db.add(btc_sec)
        db.flush()

        h = Holding(
            account_snapshot_id=acct_snap.id, security_id=btc_sec.id,
            ticker="BTC", quantity=Decimal("0.5"),
            snapshot_price=Decimal("42000"), snapshot_value=Decimal("21000"),
        )
        db.add(h)

        self._setup_dhv_with_source(
            db, account, acct_snap, "BTC", retro_date,
            Decimal("42000"), Decimal("420000"), PRICE_SOURCE_MARKET,
        )
        db.commit()

        market_data = {
            "BTC": [
                PriceResult("BTC", retro_date, Decimal("43200"), "mock"),  # 2.86% — under 5%
            ]
        }
        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, market_data, [account.id], {"BTC"}, result,
        )

        dhv = db.query(DailyHoldingValue).filter(
            DailyHoldingValue.ticker == "BTC"
        ).first()
        assert dhv.close_price == Decimal("42000")  # unchanged
        assert result.corrections == 0

    def test_skips_cash_tickers(self, db: Session):
        """Cash equivalent tickers are not corrected by retro validation."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "USD", Decimal("5000"), Decimal("1"), acct_snap)

        self._setup_dhv_with_source(
            db, account, acct_snap, "USD", retro_date,
            Decimal("1"), Decimal("5000"), PRICE_SOURCE_CASH,
        )
        db.commit()

        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, {}, [account.id], None, result,
        )
        assert result.corrections == 0

    def test_skips_synthetic_tickers(self, db: Session):
        """Synthetic tickers are not corrected by retro validation."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        syn_ticker = f"{SYNTHETIC_PREFIX}abc123"
        _create_holding(db, sync_session, account, syn_ticker, Decimal("1"), Decimal("500000"), acct_snap)

        self._setup_dhv_with_source(
            db, account, acct_snap, syn_ticker, retro_date,
            Decimal("500000"), Decimal("500000"), PRICE_SOURCE_SNAPSHOT,
        )
        db.commit()

        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, {}, [account.id], None, result,
        )
        assert result.corrections == 0

    def test_skips_when_no_fresh_market_data(self, db: Session):
        """No correction when no fresh market data exists for the ticker."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        self._setup_dhv_with_source(
            db, account, acct_snap, "AAPL", retro_date,
            Decimal("150"), Decimal("1500"), PRICE_SOURCE_SNAPSHOT,
        )
        db.commit()

        # No market data provided
        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, {}, [account.id], None, result,
        )
        assert result.corrections == 0

    def test_only_uses_fresh_market_data_not_carry_forward(self, db: Session):
        """Retro validation only corrects with actual market data, not carry-forward."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        # Market data only on day before retro_date (will be carry-forward on retro_date)
        market_trade_date = retro_date - timedelta(days=1)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        self._setup_dhv_with_source(
            db, account, acct_snap, "AAPL", retro_date,
            Decimal("150"), Decimal("1500"), PRICE_SOURCE_SNAPSHOT,
        )
        db.commit()

        # Only a price on market_trade_date, not on retro_date itself
        market_data = {
            "AAPL": [
                PriceResult("AAPL", market_trade_date, Decimal("155"), "mock"),
            ]
        }
        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, market_data, [account.id], None, result,
        )

        # Should NOT correct because the retro_date data is carry-forward
        dhv = db.query(DailyHoldingValue).first()
        assert dhv.close_price == Decimal("150")
        assert result.corrections == 0

    def test_correction_updates_market_value(self, db: Session):
        """Correction recalculates market_value using quantity * new price."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        self._setup_dhv_with_source(
            db, account, acct_snap, "AAPL", retro_date,
            Decimal("150"), Decimal("1500"), PRICE_SOURCE_SNAPSHOT,
        )
        db.commit()

        market_data = {
            "AAPL": [
                PriceResult("AAPL", retro_date, Decimal("155"), "mock"),
            ]
        }
        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, market_data, [account.id], None, result,
        )

        dhv = db.query(DailyHoldingValue).first()
        assert dhv.market_value == Decimal("1550.00")  # 10 * 155

    def test_correction_logged_at_info(self, db: Session, caplog):
        """Corrections are logged at INFO level."""
        import logging
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        self._setup_dhv_with_source(
            db, account, acct_snap, "AAPL", retro_date,
            Decimal("150"), Decimal("1500"), PRICE_SOURCE_SNAPSHOT,
        )
        db.commit()

        market_data = {
            "AAPL": [
                PriceResult("AAPL", retro_date, Decimal("155"), "mock"),
            ]
        }
        result = ValuationResult()
        service = PortfolioValuationService()
        with caplog.at_level(logging.INFO):
            service._retrospective_validate(
                db, yesterday, market_data, [account.id], None, result,
            )
        assert "Corrected AAPL" in caplog.text

    def test_correction_count_in_result(self, db: Session):
        """ValuationResult tracks correction count and details."""
        yesterday = date.today() - timedelta(days=1)
        retro_date = yesterday - timedelta(days=2)
        snap_dt = datetime.combine(retro_date, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        self._setup_dhv_with_source(
            db, account, acct_snap, "AAPL", retro_date,
            Decimal("150"), Decimal("1500"), PRICE_SOURCE_SNAPSHOT,
        )
        db.commit()

        market_data = {
            "AAPL": [
                PriceResult("AAPL", retro_date, Decimal("155"), "mock"),
            ]
        }
        result = ValuationResult()
        service = PortfolioValuationService()
        service._retrospective_validate(
            db, yesterday, market_data, [account.id], None, result,
        )
        assert result.corrections == 1
        assert len(result.correction_details) == 1
        assert "AAPL" in result.correction_details[0]

    def test_no_retro_on_first_backfill(self, db: Session):
        """No retro validation when there are no prior DHV rows."""
        yesterday = date.today() - timedelta(days=1)
        snap_dt = datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        db.commit()

        prices = {"AAPL": {yesterday: Decimal("155")}}
        service = _make_mock_service(prices)
        result = service.backfill(db)

        # First backfill — no prior rows to correct
        assert result.corrections == 0


# ---------------------------------------------------------------------------
# Tests: End-to-End
# ---------------------------------------------------------------------------
class TestEndToEnd:
    """End-to-end tests combining price guards and retrospective validation."""

    def test_bad_price_rejected_then_corrected_next_run(self, db: Session):
        """A bad price is rejected by guards, then corrected on next backfill."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        snap_dt = datetime.combine(day_before, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)

        # Create a prior DHV row to seed the prior_close
        security = get_or_create_security(db, "AAPL")
        prior_date = day_before - timedelta(days=1)
        db.add(DailyHoldingValue(
            valuation_date=prior_date,
            account_id=account.id,
            account_snapshot_id=acct_snap.id,
            security_id=security.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("150"),
            market_value=Decimal("1500"),
            price_source=PRICE_SOURCE_MARKET,
        ))
        db.commit()

        # First backfill: day_before has a bad price (100x spike)
        # Yesterday has correct price
        prices = {
            "AAPL": {
                day_before: Decimal("15000"),  # 100x spike — will be rejected
                yesterday: Decimal("155"),
            }
        }
        service = _make_mock_service(prices)
        service.backfill(db)

        # The bad price should be rejected; snapshot fallback ($150) used
        day_before_row = (
            db.query(DailyHoldingValue)
            .filter(
                DailyHoldingValue.valuation_date == day_before,
                DailyHoldingValue.ticker == "AAPL",
            )
            .first()
        )
        assert day_before_row.close_price == Decimal("150")  # snapshot fallback
        assert day_before_row.price_source == PRICE_SOURCE_SNAPSHOT

    def test_all_price_sources_set_correctly(self, db: Session):
        """All DHV rows get appropriate price_source values."""
        yesterday = date.today() - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        snap_dt = datetime.combine(day_before, time(12, 0), tzinfo=timezone.utc)

        account = _create_account(db)
        sync_session = _create_sync_session(db, snap_dt)
        acct_snap = _create_account_snapshot(db, account, sync_session)

        # Equity with market data
        _create_holding(db, sync_session, account, "AAPL", Decimal("10"), Decimal("150"), acct_snap)
        # Cash holding
        _create_holding(db, sync_session, account, "USD", Decimal("5000"), Decimal("1"), acct_snap)
        # No market data available — will use snapshot fallback
        _create_holding(db, sync_session, account, "PRIVCO", Decimal("100"), Decimal("25"), acct_snap)
        db.commit()

        prices = {
            "AAPL": {
                day_before: Decimal("152"),
                yesterday: Decimal("155"),
            },
            # No prices for PRIVCO
        }
        service = _make_mock_service(prices)
        service.backfill(db)

        rows = db.query(DailyHoldingValue).order_by(
            DailyHoldingValue.valuation_date,
            DailyHoldingValue.ticker,
        ).all()

        sources_by_ticker = {}
        for row in rows:
            if row.ticker not in sources_by_ticker:
                sources_by_ticker[row.ticker] = set()
            sources_by_ticker[row.ticker].add(row.price_source)

        assert PRICE_SOURCE_MARKET in sources_by_ticker["AAPL"]
        assert PRICE_SOURCE_CASH in sources_by_ticker["USD"]
        assert PRICE_SOURCE_SNAPSHOT in sources_by_ticker["PRIVCO"]
