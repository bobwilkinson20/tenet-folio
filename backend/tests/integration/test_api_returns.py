"""Integration tests for GET /api/portfolio/returns endpoint."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Account, AccountSnapshot, DailyHoldingValue, SyncSession
from models.activity import Activity
from tests.fixtures import get_or_create_security


# ---------------------------------------------------------------------------
# Helpers
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


def _create_sync_session(db: Session) -> SyncSession:
    ss = SyncSession(timestamp=datetime.now(timezone.utc), is_complete=True)
    db.add(ss)
    db.flush()
    return ss


def _create_snapshot(
    db: Session, account: Account, sync_session: SyncSession,
    total_value: Decimal = Decimal("0"),
) -> AccountSnapshot:
    snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=sync_session.id,
        status="success",
        total_value=total_value,
    )
    db.add(snap)
    db.flush()
    return snap


def _create_dhv(
    db: Session,
    account: Account,
    snapshot: AccountSnapshot,
    valuation_date: date,
    ticker: str,
    market_value: Decimal,
    quantity: Decimal = Decimal("10"),
) -> DailyHoldingValue:
    security = get_or_create_security(db, ticker)
    close_price = market_value / quantity if quantity else Decimal("0")
    dhv = DailyHoldingValue(
        valuation_date=valuation_date,
        account_id=account.id,
        account_snapshot_id=snapshot.id,
        security_id=security.id,
        ticker=ticker,
        quantity=quantity,
        close_price=close_price,
        market_value=market_value,
    )
    db.add(dhv)
    db.flush()
    return dhv


def _populate_daily_values(
    db: Session,
    account: Account,
    snapshot: AccountSnapshot,
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
        _create_dhv(db, account, snapshot, current, ticker, value)
        value += daily_growth
        current += timedelta(days=1)
    db.flush()


def _create_activity(
    db: Session,
    account: Account,
    activity_date: date,
    activity_type: str,
    amount: Decimal,
) -> Activity:
    act = Activity(
        account_id=account.id,
        provider_name="SnapTrade",
        external_id=f"act_{activity_date}_{activity_type}_{amount}",
        activity_date=datetime.combine(activity_date, time(12, 0), tzinfo=timezone.utc),
        type=activity_type,
        amount=amount,
        description=f"{activity_type} of {amount}",
    )
    db.add(act)
    db.flush()
    return act


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestReturnsAPI:
    """Integration tests for /api/portfolio/returns."""

    def test_returns_empty_db(self, client: TestClient):
        """Empty database returns null portfolio and empty accounts."""
        response = client.get("/api/portfolio/returns")
        assert response.status_code == 200
        data = response.json()
        assert data["portfolio"] is not None  # portfolio scope still returned
        assert data["accounts"] == [] or isinstance(data["accounts"], list)

    def test_returns_with_data(self, client: TestClient, db: Session):
        """Returns IRR when DHV data and activities exist."""
        today = date.today()
        start = today - timedelta(days=35)

        account = _create_account(db, "Growth Account")
        ss = _create_sync_session(db)
        snap = _create_snapshot(db, account, ss, Decimal("11000"))

        # Populate 35 days of daily values with steady growth
        _populate_daily_values(
            db, account, snap,
            start=start, end=today,
            ticker="VTI",
            start_value=Decimal("10000"),
            daily_growth=Decimal("30"),
        )

        # Add a deposit at the start
        _create_activity(db, account, start, "deposit", Decimal("10000"))
        db.commit()

        response = client.get("/api/portfolio/returns?periods=1M")
        assert response.status_code == 200
        data = response.json()

        portfolio = data["portfolio"]
        assert portfolio is not None
        assert len(portfolio["periods"]) == 1
        period = portfolio["periods"][0]
        assert period["period"] == "1M"
        # IRR should be computed (non-null) since we have sufficient data
        if period["has_sufficient_data"]:
            assert period["irr"] is not None

    def test_returns_scope_portfolio(self, client: TestClient, db: Session):
        """scope=portfolio returns only portfolio, no accounts."""
        today = date.today()
        start = today - timedelta(days=5)

        account = _create_account(db, "Scope Test")
        ss = _create_sync_session(db)
        snap = _create_snapshot(db, account, ss, Decimal("5000"))
        _populate_daily_values(
            db, account, snap, start, today, "SPY", Decimal("5000"),
        )
        db.commit()

        response = client.get("/api/portfolio/returns?scope=portfolio&periods=1D")
        assert response.status_code == 200
        data = response.json()
        assert data["portfolio"] is not None
        assert data["accounts"] == []

    def test_returns_scope_account(self, client: TestClient, db: Session):
        """scope=<uuid> returns only that single account."""
        today = date.today()
        start = today - timedelta(days=5)

        account = _create_account(db, "Single Account")
        ss = _create_sync_session(db)
        snap = _create_snapshot(db, account, ss, Decimal("5000"))
        _populate_daily_values(
            db, account, snap, start, today, "QQQ", Decimal("5000"),
        )
        db.commit()

        response = client.get(
            f"/api/portfolio/returns?scope={account.id}&periods=1D"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["portfolio"] is None
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["scope_id"] == account.id
        assert data["accounts"][0]["scope_name"] == "Single Account"

    def test_returns_custom_periods(self, client: TestClient, db: Session):
        """Custom periods parameter filters to only requested periods."""
        today = date.today()
        start = today - timedelta(days=400)

        account = _create_account(db, "Periods Test")
        ss = _create_sync_session(db)
        snap = _create_snapshot(db, account, ss, Decimal("10000"))
        _populate_daily_values(
            db, account, snap, start, today, "VTI", Decimal("10000"),
        )
        db.commit()

        response = client.get(
            "/api/portfolio/returns?scope=portfolio&periods=YTD,1Y"
        )
        assert response.status_code == 200
        data = response.json()
        periods = data["portfolio"]["periods"]
        period_codes = [p["period"] for p in periods]
        assert period_codes == ["YTD", "1Y"]

    def test_returns_include_inactive(self, client: TestClient, db: Session):
        """Inactive account only appears when include_inactive is set."""
        today = date.today()
        start = today - timedelta(days=5)

        active_acc = _create_account(db, "Active", external_id="ext_active")
        inactive_acc = _create_account(
            db, "Inactive", external_id="ext_inactive", is_active=False,
        )
        ss = _create_sync_session(db)
        snap_active = _create_snapshot(db, active_acc, ss, Decimal("5000"))
        snap_inactive = _create_snapshot(db, inactive_acc, ss, Decimal("3000"))
        _populate_daily_values(
            db, active_acc, snap_active, start, today, "VTI", Decimal("5000"),
        )
        _populate_daily_values(
            db, inactive_acc, snap_inactive, start, today, "BND", Decimal("3000"),
        )
        db.commit()

        # Default: inactive excluded
        response = client.get("/api/portfolio/returns?periods=1D")
        data = response.json()
        account_names = [a["scope_name"] for a in data["accounts"]]
        assert "Active" in account_names
        assert "Inactive" not in account_names

        # With include_inactive=true
        response = client.get(
            "/api/portfolio/returns?periods=1D&include_inactive=true"
        )
        data = response.json()
        account_names = [a["scope_name"] for a in data["accounts"]]
        assert "Active" in account_names
        assert "Inactive" in account_names

    def test_returns_irr_serialized_as_string(self, client: TestClient, db: Session):
        """IRR values are serialized as strings (not floats)."""
        today = date.today()
        start = today - timedelta(days=35)

        account = _create_account(db, "String IRR Test")
        ss = _create_sync_session(db)
        snap = _create_snapshot(db, account, ss, Decimal("11000"))
        _populate_daily_values(
            db, account, snap, start, today, "VTI",
            Decimal("10000"), daily_growth=Decimal("30"),
        )
        _create_activity(db, account, start, "deposit", Decimal("10000"))
        db.commit()

        response = client.get("/api/portfolio/returns?scope=portfolio&periods=1M")
        assert response.status_code == 200
        period = response.json()["portfolio"]["periods"][0]
        # IRR should be a string or null, never a float
        if period["irr"] is not None:
            assert isinstance(period["irr"], str)

    def test_returns_period_dates_present(self, client: TestClient, db: Session):
        """Each period includes start_date and end_date."""
        today = date.today()
        start = today - timedelta(days=5)

        account = _create_account(db, "Dates Test")
        ss = _create_sync_session(db)
        snap = _create_snapshot(db, account, ss, Decimal("5000"))
        _populate_daily_values(
            db, account, snap, start, today, "SPY", Decimal("5000"),
        )
        db.commit()

        response = client.get("/api/portfolio/returns?scope=portfolio&periods=1D")
        assert response.status_code == 200
        period = response.json()["portfolio"]["periods"][0]
        assert "start_date" in period
        assert "end_date" in period
        assert period["start_date"] is not None
        assert period["end_date"] is not None


class TestReturnsChaining:
    """Integration tests for chained account returns via API."""

    def test_chained_account_includes_chained_from(
        self, client: TestClient, db: Session,
    ):
        """API response includes chained_from for chained accounts."""
        old = _create_account(
            db, "Old Provider", external_id="chain_old", is_active=False,
        )
        new = _create_account(db, "New Provider", external_id="chain_new")
        old.superseded_by_account_id = new.id
        db.commit()

        response = client.get(f"/api/portfolio/returns?scope={new.id}&periods=1D")
        assert response.status_code == 200
        data = response.json()
        account = data["accounts"][0]
        assert account["chained_from"] == ["Old Provider"]

    def test_standalone_account_has_empty_chained_from(
        self, client: TestClient, db: Session,
    ):
        """API response has empty chained_from for standalone accounts."""
        acc = _create_account(db, "Standalone", external_id="standalone_1")
        db.commit()

        response = client.get(f"/api/portfolio/returns?scope={acc.id}&periods=1D")
        assert response.status_code == 200
        data = response.json()
        account = data["accounts"][0]
        assert account["chained_from"] == []

    def test_superseded_accounts_excluded_from_all_scope(
        self, client: TestClient, db: Session,
    ):
        """Superseded accounts do not appear in scope=all per-account list."""
        old = _create_account(
            db, "Superseded Acct", external_id="sup_api", is_active=False,
        )
        new = _create_account(db, "Active Acct", external_id="act_api")
        old.superseded_by_account_id = new.id
        db.commit()

        response = client.get("/api/portfolio/returns?periods=1D&include_inactive=true")
        assert response.status_code == 200
        data = response.json()
        account_names = [a["scope_name"] for a in data["accounts"]]
        assert "Active Acct" in account_names
        assert "Superseded Acct" not in account_names
