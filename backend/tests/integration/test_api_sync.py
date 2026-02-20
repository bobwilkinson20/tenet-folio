"""Integration tests for sync API endpoints."""

from unittest.mock import patch

from models import Account, AccountSnapshot, Holding


def test_sync_creates_sync_session_with_accounts(client_with_mock_sync, db):
    """Unified sync creates accounts and a sync session with holdings."""
    response = client_with_mock_sync.post("/api/sync")
    assert response.status_code == 200

    sync_session = response.json()
    assert sync_session["is_complete"] is True
    assert sync_session["error_message"] is None
    assert len(sync_session["holdings"]) > 0

    # Verify accounts were created
    accounts = db.query(Account).all()
    assert len(accounts) == 2

    # Verify holdings are in DB
    acct_snap_ids = [
        a.id for a in db.query(AccountSnapshot)
        .filter_by(sync_session_id=sync_session["id"]).all()
    ]
    holdings = db.query(Holding).filter(
        Holding.account_snapshot_id.in_(acct_snap_ids)
    ).all()
    assert len(holdings) > 0


def test_sync_creates_holdings_for_active_accounts_only(client_with_mock_sync, db):
    """Sync only creates holdings for active accounts."""
    # First sync creates accounts and holdings
    client_with_mock_sync.post("/api/sync")

    # Deactivate one account
    accounts = db.query(Account).all()
    assert len(accounts) == 2
    accounts[0].is_active = False
    db.commit()

    # Second sync should only have holdings from the active account
    response = client_with_mock_sync.post("/api/sync")
    assert response.status_code == 200

    sync_session = response.json()
    acct_snap_ids = [
        a.id for a in db.query(AccountSnapshot)
        .filter_by(sync_session_id=sync_session["id"]).all()
    ]
    holdings = db.query(Holding).filter(
        Holding.account_snapshot_id.in_(acct_snap_ids)
    ).all()
    active_account = db.query(Account).filter(Account.is_active.is_(True)).first()

    for h in holdings:
        assert h.account_snapshot.account_id == active_account.id


def test_sync_always_syncs_without_throttle(client_with_mock_sync, db):
    """Consecutive syncs always succeed (no throttle)."""
    # First sync
    response = client_with_mock_sync.post("/api/sync")
    assert response.status_code == 200
    assert response.json()["is_complete"] is True

    # Second sync should also succeed immediately
    response = client_with_mock_sync.post("/api/sync")
    assert response.status_code == 200
    assert response.json()["is_complete"] is True


def test_sync_fails_with_unavailable_provider(client_with_failing_sync, db):
    """Sync returns 200 with is_complete=False when provider is unavailable."""
    # Create an account so the sync failure marks it
    account = Account(
        provider_name="SnapTrade",
        external_id="test_acc",
        name="Test Account",
        is_active=True,
    )
    db.add(account)
    db.commit()

    response = client_with_failing_sync.post("/api/sync")
    assert response.status_code == 200
    data = response.json()
    assert data["is_complete"] is False
    assert data["error_message"] is not None
    # Should have a failed sync log entry
    assert len(data["sync_log"]) == 1
    assert data["sync_log"][0]["status"] == "failed"
    assert data["sync_log"][0]["provider_name"] == "SnapTrade"


def test_sync_upserts_accounts_from_provider(client_with_mock_sync, db):
    """Sync creates account records from provider data."""
    # No accounts exist initially
    assert db.query(Account).count() == 0

    response = client_with_mock_sync.post("/api/sync")
    assert response.status_code == 200

    # Accounts should now exist
    accounts = db.query(Account).all()
    assert len(accounts) == 2
    assert {a.external_id for a in accounts} == {"st_acc_001", "st_acc_002"}
    assert {a.institution_name for a in accounts} == {"Interactive Brokers", "Fidelity"}


def test_sync_response_includes_sync_log(client_with_mock_sync, db):
    """Sync response includes sync_log array."""
    response = client_with_mock_sync.post("/api/sync")
    assert response.status_code == 200

    data = response.json()
    assert "sync_log" in data
    assert len(data["sync_log"]) >= 1

    entry = data["sync_log"][0]
    assert "id" in entry
    assert "provider_name" in entry
    assert "status" in entry
    assert "accounts_synced" in entry
    assert "created_at" in entry


def test_dashboard_empty(client, db):
    """Dashboard shows zeros when no data."""
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    # Decimal fields are serialized as strings
    assert float(data["total_net_worth"]) == 0
    assert data["accounts"] == []


def test_dashboard_with_holdings(client_with_mock_sync, db):
    """Dashboard shows correct account values after sync."""
    # Unified sync creates accounts and holdings
    client_with_mock_sync.post("/api/sync")

    response = client_with_mock_sync.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()

    # Check we have account values
    assert len(data["accounts"]) == 2
    total = sum(float(acc["value"]) for acc in data["accounts"])
    assert total > 0
    assert float(data["total_net_worth"]) == total

    # Sample holdings: 15050 + 7012.50 + 44000 = 66062.50
    assert float(data["total_net_worth"]) == 66062.50


def test_dashboard_shows_per_account_sync_status(client_with_mock_sync, db):
    """Dashboard includes per-account sync status information."""
    # Unified sync creates accounts and syncs holdings
    client_with_mock_sync.post("/api/sync")

    response = client_with_mock_sync.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()

    # Each account should have sync status (no throttle fields)
    for acc in data["accounts"]:
        assert acc["last_sync_time"] is not None
        assert acc["last_sync_status"] == "success"
        assert "can_sync" not in acc
        assert "next_sync_time" not in acc


def test_dashboard_includes_institution_name(client_with_mock_sync, db):
    """Dashboard includes institution_name for each account."""
    # Unified sync creates accounts with institution names
    client_with_mock_sync.post("/api/sync")

    response = client_with_mock_sync.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()

    # Should have institution names from SnapTrade mock data
    assert len(data["accounts"]) == 2
    institution_names = {acc["institution_name"] for acc in data["accounts"]}
    assert "Interactive Brokers" in institution_names
    assert "Fidelity" in institution_names

def test_dashboard_includes_allocations(client_with_mock_sync, db):
    """Dashboard includes allocation data when asset types are configured."""
    from models import AssetClass, Security
    from decimal import Decimal

    # Create asset types
    stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
    bonds = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
    db.add_all([stocks, bonds])
    db.commit()

    # Assign securities
    sec_aapl = db.query(Security).filter_by(ticker="AAPL").first()
    if not sec_aapl:
        sec_aapl = Security(ticker="AAPL", manual_asset_class=stocks)
        db.add(sec_aapl)
    else:
        sec_aapl.manual_asset_class = stocks

    sec_tsla = db.query(Security).filter_by(ticker="TSLA").first()
    if not sec_tsla:
        sec_tsla = Security(ticker="TSLA", manual_asset_class=stocks)
        db.add(sec_tsla)
    else:
        sec_tsla.manual_asset_class = stocks

    sec_bnd = db.query(Security).filter_by(ticker="BND").first()
    if not sec_bnd:
        sec_bnd = Security(ticker="BND", manual_asset_class=bonds)
        db.add(sec_bnd)
    else:
        sec_bnd.manual_asset_class = bonds

    db.commit()

    # Unified sync creates accounts and holdings
    client_with_mock_sync.post("/api/sync")

    response = client_with_mock_sync.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()

    # Should have allocations (at least stocks since AAPL and TSLA exist in mock data)
    assert "allocations" in data
    assert len(data["allocations"]) >= 1

    # Verify stocks allocation exists
    stocks_alloc = next((a for a in data["allocations"] if a["asset_type_name"] == "Stocks"), None)
    assert stocks_alloc is not None
    assert stocks_alloc["target_percent"] == "60.00"
    assert float(stocks_alloc["value"]) > 0

    # If bonds allocation exists (depends on if BND is in mock data), verify it
    bonds_alloc = next((a for a in data["allocations"] if a["asset_type_name"] == "Bonds"), None)
    if bonds_alloc:
        assert bonds_alloc["target_percent"] == "40.00"
        assert float(bonds_alloc["value"]) > 0


def test_dashboard_unassigned_securities(client_with_mock_sync, db):
    """Dashboard shows unassigned securities count and value."""
    from models import AssetClass, Security
    from decimal import Decimal

    # Create asset type but only assign some securities
    stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("100.00"))
    db.add(stocks)
    db.commit()

    # Assign only AAPL
    sec_aapl = db.query(Security).filter_by(ticker="AAPL").first()
    if not sec_aapl:
        sec_aapl = Security(ticker="AAPL", manual_asset_class=stocks)
        db.add(sec_aapl)
    else:
        sec_aapl.manual_asset_class = stocks
    db.commit()

    # Unified sync (TSLA and BND will be unassigned)
    client_with_mock_sync.post("/api/sync")

    response = client_with_mock_sync.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()

    # Should have unassigned holdings
    assert data["unassigned_count"] > 0
    assert float(data["unassigned_value"]) > 0


def test_dashboard_includes_balance_date(client_with_mock_sync, db):
    """Dashboard includes balance_date field for accounts."""
    client_with_mock_sync.post("/api/sync")

    response = client_with_mock_sync.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()

    # balance_date should exist in response (may be null for SnapTrade)
    for acc in data["accounts"]:
        assert "balance_date" in acc


def test_dashboard_shows_zero_for_liquidated_account(db):
    """After liquidation (no holdings), dashboard shows $0 for the account."""
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    from api.sync import get_sync_service as get_sync_service_for_sync
    from services.sync_service import SyncService
    from tests.fixtures.mocks import (
        MockSnapTradeClient,
        MockProviderRegistry,
        SAMPLE_SNAPTRADE_ACCOUNTS,
        SAMPLE_SNAPTRADE_HOLDINGS,
    )

    def override_get_db():
        try:
            yield db
        finally:
            pass

    # Phase 1: Sync with holdings
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})

    def override_sync_service():
        return SyncService(provider_registry=registry)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sync_service_for_sync] = override_sync_service
    test_client = TestClient(app)

    response = test_client.post("/api/sync")
    assert response.status_code == 200

    # Verify initial values are non-zero
    dash = test_client.get("/api/dashboard").json()
    assert float(dash["total_net_worth"]) == 66062.50

    # Phase 2: Sync again with no holdings (liquidated)
    mock_st_empty = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=[],  # All accounts liquidated
    )
    registry_empty = MockProviderRegistry({"SnapTrade": mock_st_empty})

    def override_sync_service_empty():
        return SyncService(provider_registry=registry_empty)

    app.dependency_overrides[get_sync_service_for_sync] = override_sync_service_empty

    response = test_client.post("/api/sync")
    assert response.status_code == 200

    # Dashboard should now show $0 for all accounts
    dash = test_client.get("/api/dashboard").json()
    assert float(dash["total_net_worth"]) == 0.0
    for acc in dash["accounts"]:
        assert float(acc["value"]) == 0.0

    app.dependency_overrides.clear()


def test_account_holdings_empty_after_liquidation(db):
    """After liquidation, GET /accounts/{id}/holdings returns empty list."""
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    from api.sync import get_sync_service as get_sync_service_for_sync
    from services.sync_service import SyncService
    from tests.fixtures.mocks import (
        MockSnapTradeClient,
        MockProviderRegistry,
        SAMPLE_SNAPTRADE_ACCOUNTS,
        SAMPLE_SNAPTRADE_HOLDINGS,
    )

    def override_get_db():
        try:
            yield db
        finally:
            pass

    # Phase 1: Sync with holdings
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})

    def override_sync_service():
        return SyncService(provider_registry=registry)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sync_service_for_sync] = override_sync_service
    test_client = TestClient(app)

    response = test_client.post("/api/sync")
    assert response.status_code == 200

    # Get an account ID
    accounts = db.query(Account).all()
    account_id = accounts[0].id

    # Verify holdings exist initially
    holdings_resp = test_client.get(f"/api/accounts/{account_id}/holdings")
    assert holdings_resp.status_code == 200
    assert len(holdings_resp.json()) > 0

    # Phase 2: Sync again with no holdings (liquidated)
    mock_st_empty = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=[],
    )
    registry_empty = MockProviderRegistry({"SnapTrade": mock_st_empty})

    def override_sync_service_empty():
        return SyncService(provider_registry=registry_empty)

    app.dependency_overrides[get_sync_service_for_sync] = override_sync_service_empty

    response = test_client.post("/api/sync")
    assert response.status_code == 200

    # Holdings should now be empty
    holdings_resp = test_client.get(f"/api/accounts/{account_id}/holdings")
    assert holdings_resp.status_code == 200
    assert len(holdings_resp.json()) == 0

    app.dependency_overrides.clear()


# --- Concurrent sync prevention tests ---


def test_concurrent_sync_returns_409(db):
    """Two concurrent POST /api/sync requests: first gets 200, second gets 409."""
    import threading
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    from api.sync import get_sync_service as get_sync_service_for_sync
    from services.sync_service import SyncService
    from tests.fixtures.mocks import (
        MockSnapTradeClient,
        MockProviderRegistry,
        SAMPLE_SNAPTRADE_ACCOUNTS,
        SAMPLE_SNAPTRADE_HOLDINGS,
    )

    def override_get_db():
        try:
            yield db
        finally:
            pass

    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})

    # Shared service instance with delayed sync for proper testing
    service = SyncService(provider_registry=registry)
    sync_started = threading.Event()
    proceed_with_sync = threading.Event()
    original_method = service._sync_provider_accounts

    def delayed_sync(*args, **kwargs):
        sync_started.set()
        proceed_with_sync.wait()
        return original_method(*args, **kwargs)

    service._sync_provider_accounts = delayed_sync

    def override_sync_service():
        return service

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sync_service_for_sync] = override_sync_service
    test_client = TestClient(app)

    # Track results from concurrent requests
    first_result = {}
    second_result = {}

    def run_first_sync():
        """First sync - should succeed."""
        response = test_client.post("/api/sync")
        first_result["status"] = response.status_code
        first_result["data"] = response.json() if response.status_code == 200 else None

    def run_second_sync():
        """Second sync - should get 409."""
        response = test_client.post("/api/sync")
        second_result["status"] = response.status_code
        second_result["data"] = response.json() if response.status_code != 409 else None
        second_result["detail"] = response.json().get("detail") if response.status_code == 409 else None

    # Start first sync
    t1 = threading.Thread(target=run_first_sync)
    t1.start()

    # Wait for first sync to acquire lock
    sync_started.wait(timeout=1.0)

    # Try second sync - should get 409
    run_second_sync()

    # Let first sync complete
    proceed_with_sync.set()
    t1.join()

    # Verify results
    assert first_result["status"] == 200
    assert first_result["data"]["is_complete"] is True

    assert second_result["status"] == 409
    assert "already in progress" in second_result["detail"].lower()

    # Restore original method
    service._sync_provider_accounts = original_method
    app.dependency_overrides.clear()


def test_sync_409_does_not_create_session(db):
    """409 response doesn't create a SyncSession."""
    import threading
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    from api.sync import get_sync_service as get_sync_service_for_sync
    from services.sync_service import SyncService
    from tests.fixtures.mocks import (
        MockSnapTradeClient,
        MockProviderRegistry,
        SAMPLE_SNAPTRADE_ACCOUNTS,
        SAMPLE_SNAPTRADE_HOLDINGS,
    )
    from models import SyncSession

    def override_get_db():
        try:
            yield db
        finally:
            pass

    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})

    # Shared service instance with delayed sync for proper testing
    service = SyncService(provider_registry=registry)
    sync_started = threading.Event()
    proceed_with_sync = threading.Event()
    original_method = service._sync_provider_accounts

    def delayed_sync(*args, **kwargs):
        sync_started.set()
        proceed_with_sync.wait()
        return original_method(*args, **kwargs)

    service._sync_provider_accounts = delayed_sync

    def override_sync_service():
        return service

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sync_service_for_sync] = override_sync_service
    test_client = TestClient(app)

    # Count sessions before
    sessions_before = db.query(SyncSession).count()

    def run_first_sync():
        test_client.post("/api/sync")

    # Start first sync in background
    t1 = threading.Thread(target=run_first_sync)
    t1.start()

    # Wait for first sync to acquire lock
    sync_started.wait(timeout=1.0)

    # Try second sync - should get 409
    response = test_client.post("/api/sync")
    assert response.status_code == 409

    # Let first sync complete
    proceed_with_sync.set()
    t1.join()

    # Only one new session should exist (from first sync)
    sessions_after = db.query(SyncSession).count()
    assert sessions_after == sessions_before + 1

    # Restore original method
    service._sync_provider_accounts = original_method
    app.dependency_overrides.clear()


def test_sync_after_409_succeeds(db):
    """Sync succeeds after previous sync completes."""
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    from api.sync import get_sync_service as get_sync_service_for_sync
    from services.sync_service import SyncService
    from tests.fixtures.mocks import (
        MockSnapTradeClient,
        MockProviderRegistry,
        SAMPLE_SNAPTRADE_ACCOUNTS,
        SAMPLE_SNAPTRADE_HOLDINGS,
    )

    def override_get_db():
        try:
            yield db
        finally:
            pass

    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})

    def override_sync_service():
        return SyncService(provider_registry=registry)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sync_service_for_sync] = override_sync_service
    test_client = TestClient(app)

    # First sync
    response = test_client.post("/api/sync")
    assert response.status_code == 200
    assert response.json()["is_complete"] is True

    # Second sync (after first completes) should also succeed
    response = test_client.post("/api/sync")
    assert response.status_code == 200
    assert response.json()["is_complete"] is True

    app.dependency_overrides.clear()


# --- Sanitized error response tests ---


def test_sync_500_does_not_leak_internals(db):
    """500 response uses generic message, never exposes str(e)."""
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    from api.sync import get_sync_service as get_sync_service_for_sync
    from services.sync_service import SyncService
    from tests.fixtures.mocks import MockProviderRegistry

    def override_get_db():
        try:
            yield db
        finally:
            pass

    registry = MockProviderRegistry({})

    def override_sync_service():
        return SyncService(provider_registry=registry)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sync_service_for_sync] = override_sync_service

    # Patch trigger_sync to raise a generic exception with sensitive info
    with patch.object(
        SyncService, "trigger_sync",
        side_effect=Exception("database password: hunter2"),
    ):
        test_client = TestClient(app)
        response = test_client.post("/api/sync")

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "hunter2" not in detail
    assert "unexpected" in detail.lower()

    app.dependency_overrides.clear()


def test_sync_502_for_provider_auth_error(db):
    """ProviderAuthError from trigger_sync returns 502 with safe message."""
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    from api.sync import get_sync_service as get_sync_service_for_sync
    from services.sync_service import SyncService
    from integrations.exceptions import ProviderAuthError
    from tests.fixtures.mocks import MockProviderRegistry

    def override_get_db():
        try:
            yield db
        finally:
            pass

    registry = MockProviderRegistry({})

    def override_sync_service():
        return SyncService(provider_registry=registry)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sync_service_for_sync] = override_sync_service

    with patch.object(
        SyncService, "trigger_sync",
        side_effect=ProviderAuthError(
            "Token expired", provider_name="SimpleFIN"
        ),
    ):
        test_client = TestClient(app)
        response = test_client.post("/api/sync")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "SimpleFIN" in detail
    assert "authentication" in detail.lower()

    app.dependency_overrides.clear()
