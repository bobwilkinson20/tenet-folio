"""Integration tests for accounts API."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from models import AccountSnapshot, DailyHoldingValue, Holding, HoldingLot, LotDisposal, SyncSession
from tests.fixtures import get_or_create_security


def _create_account_snapshot_with_holding(db, account, sync_session, ticker, quantity, price, market_value):
    """Helper to create an AccountSnapshot and Holding record."""
    security = get_or_create_security(db, ticker)
    acct_snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=sync_session.id,
        status="success",
        total_value=market_value,
    )
    db.add(acct_snap)
    db.flush()

    holding = Holding(
        account_snapshot_id=acct_snap.id,
        security_id=security.id,
        ticker=ticker,
        quantity=quantity,
        snapshot_price=price,
        snapshot_value=market_value,
    )
    db.add(holding)
    db.commit()
    return acct_snap, holding


def _create_account_snapshot(db, account_id, sync_session_id, total_value):
    """Helper to create an AccountSnapshot record (no holdings)."""
    acct_snap = AccountSnapshot(
        account_id=account_id,
        sync_session_id=sync_session_id,
        status="success",
        total_value=total_value,
    )
    db.add(acct_snap)
    db.commit()
    return acct_snap


def _create_dhv(db, account_id, account_snapshot_id, security, valuation_date, quantity, close_price, market_value):
    """Helper to create a DailyHoldingValue record."""
    dhv = DailyHoldingValue(
        valuation_date=valuation_date,
        account_id=account_id,
        account_snapshot_id=account_snapshot_id,
        security_id=security.id,
        ticker=security.ticker,
        quantity=quantity,
        close_price=close_price,
        market_value=market_value,
    )
    db.add(dhv)
    db.commit()
    return dhv


def test_list_accounts_empty(client: object):
    """Test listing accounts when none exist."""
    response = client.get("/api/accounts")
    assert response.status_code == 200
    assert response.json() == []


def test_list_accounts_with_data(client: object, account):
    """Test listing accounts when they exist."""
    response = client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["external_id"] == "ext_123"
    assert data[0]["name"] == "Test Account"
    assert data[0]["institution_name"] == "Test Brokerage"


def test_list_accounts_includes_value(client: object, account, holding, db):
    """Test that listing accounts includes calculated value from holdings."""
    # The holding fixture includes account_snapshot with market_value of 1505.00
    response = client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # The holding fixture has market_value of 1505.00
    assert Decimal(data[0]["value"]) == Decimal("1505.00")


def test_list_accounts_value_null_without_holdings(client: object, account):
    """Test that listing accounts shows null value when no holdings exist."""
    response = client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["value"] is None


def test_list_accounts_uses_dhv_value_over_snapshot(client: object, account, holding, db):
    """Test that list accounts uses DHV market value instead of snapshot value."""
    # The holding fixture creates an account_snapshot with total_value=1505.00
    # Create a DHV row with a different (updated) market value
    acct_snap = db.query(AccountSnapshot).filter(
        AccountSnapshot.account_id == account.id
    ).first()
    security = get_or_create_security(db, "AAPL")
    _create_dhv(
        db, account.id, acct_snap.id, security,
        valuation_date=date.today(),
        quantity=Decimal("10.00"),
        close_price=Decimal("175.00"),
        market_value=Decimal("1750.00"),
    )

    response = client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # Should use DHV value (1750), not snapshot value (1505)
    assert Decimal(data[0]["value"]) == Decimal("1750.00")


def test_list_accounts_falls_back_to_snapshot_for_inactive(client: object, db):
    """Test that inactive accounts fall back to AccountSnapshot value."""
    from models import Account
    # Create an inactive account with a snapshot but no DHV
    acc = Account(
        provider_name="SnapTrade",
        external_id="ext_inactive",
        name="Inactive Account",
        is_active=False,
    )
    db.add(acc)
    db.flush()

    sync_session = SyncSession(
        timestamp=datetime.now(timezone.utc),
        is_complete=True,
    )
    db.add(sync_session)
    db.flush()

    _create_account_snapshot(db, acc.id, sync_session.id, Decimal("5000.00"))

    response = client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    inactive = [a for a in data if a["id"] == acc.id]
    assert len(inactive) == 1
    assert Decimal(inactive[0]["value"]) == Decimal("5000.00")


def test_get_account(client: object, account):
    """Test getting a single account."""
    response = client.get(f"/api/accounts/{account.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == account.id
    assert data["name"] == "Test Account"
    assert data["institution_name"] == "Test Brokerage"


def test_get_account_not_found(client: object):
    """Test getting a non-existent account."""
    response = client.get("/api/accounts/nonexistent-id")
    assert response.status_code == 404


def test_create_account(client: object, asset_class):
    """Test creating a new account."""
    account_data = {
        "provider_name": "SnapTrade",
        "external_id": "new_ext_id",
        "name": "New Account",
    }
    response = client.post("/api/accounts", json=account_data)
    assert response.status_code == 200
    data = response.json()
    assert data["external_id"] == "new_ext_id"
    assert data["name"] == "New Account"
    assert data["is_active"] is True


def test_patch_is_active_false_rejected(client: object, account):
    """PATCH is_active=false is rejected; must use POST /deactivate."""
    update_data = {"is_active": False}
    response = client.patch(f"/api/accounts/{account.id}", json=update_data)
    assert response.status_code == 400
    assert "deactivate" in response.json()["detail"].lower()


def test_get_account_holdings(client: object, account, holding, db):
    """Test getting holdings for an account."""
    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "AAPL"
    assert Decimal(data[0]["quantity"]) == Decimal("10.00")
    assert Decimal(data[0]["snapshot_price"]) == Decimal("150.50")
    assert Decimal(data[0]["snapshot_value"]) == Decimal("1505.00")


def test_get_account_holdings_not_found(client: object):
    """Test getting holdings for non-existent account."""
    response = client.get("/api/accounts/nonexistent-id/holdings")
    assert response.status_code == 404


def test_get_account_holdings_empty(client: object, account):
    """Test getting holdings for account with no snapshots."""
    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    assert response.json() == []


def test_get_account_holdings_returns_latest_only(client: object, account, db):
    """Test that holdings endpoint returns only the latest snapshot."""
    from datetime import timedelta

    # Create older sync_session with holdings
    old_sync_session = SyncSession(
        timestamp=datetime.now(timezone.utc) - timedelta(days=2),
        is_complete=True,
    )
    db.add(old_sync_session)
    db.flush()
    _create_account_snapshot_with_holding(
        db, account, old_sync_session, "OLD", Decimal("5.00"), Decimal("100.00"), Decimal("500.00")
    )

    # Create newer sync_session with different holdings
    new_sync_session = SyncSession(
        timestamp=datetime.now(timezone.utc),
        is_complete=True,
    )
    db.add(new_sync_session)
    db.flush()
    _create_account_snapshot_with_holding(
        db, account, new_sync_session, "NEW", Decimal("10.00"), Decimal("200.00"), Decimal("2000.00")
    )

    # Should only return holdings from newest snapshot
    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "NEW"
    assert Decimal(data[0]["snapshot_value"]) == Decimal("2000.00")


def test_get_account_holdings_includes_security_name(client: object, account, security, sync_session, db):
    """Test that holdings response includes security_name from Security table."""
    # Create an account snapshot and holding that uses the existing security fixture
    acct_snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=sync_session.id,
        status="success",
        total_value=Decimal("1505.00"),
    )
    db.add(acct_snap)
    db.flush()

    holding = Holding(
        account_snapshot_id=acct_snap.id,
        security_id=security.id,
        ticker="AAPL",  # Matches the security fixture
        quantity=Decimal("10.00"),
        snapshot_price=Decimal("150.50"),
        snapshot_value=Decimal("1505.00"),
    )
    db.add(holding)
    db.commit()

    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "AAPL"
    assert data[0]["security_name"] == "Apple Inc."


def test_get_account_holdings_security_name_null_when_no_security(client: object, account, sync_session, db):
    """Test that security_name is null when Security record has no name."""
    # Create a security without a name, and a holding for it
    sec_unknown = get_or_create_security(db, "UNKNOWN")
    sec_unknown.name = None  # Clear the name
    db.flush()

    acct_snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=sync_session.id,
        status="success",
        total_value=Decimal("500.00"),
    )
    db.add(acct_snap)
    db.flush()

    holding = Holding(
        account_snapshot_id=acct_snap.id,
        security_id=sec_unknown.id,
        ticker="UNKNOWN",
        quantity=Decimal("5.00"),
        snapshot_price=Decimal("100.00"),
        snapshot_value=Decimal("500.00"),
    )
    db.add(holding)
    db.commit()

    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "UNKNOWN"
    assert data[0]["security_name"] is None


def test_get_account_holdings_with_synthetic_ticker(client: object, account, sync_session, db):
    """Test that holdings with synthetic tickers can have security names."""
    from models import Security

    # Create a security with a synthetic ticker
    synthetic_security = Security(
        ticker="_SF:abc12345",
        name="Vanguard Target Retirement 2045",
    )
    db.add(synthetic_security)
    db.flush()

    acct_snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=sync_session.id,
        status="success",
        total_value=Decimal("5000.00"),
    )
    db.add(acct_snap)
    db.flush()

    holding = Holding(
        account_snapshot_id=acct_snap.id,
        security_id=synthetic_security.id,
        ticker="_SF:abc12345",
        quantity=Decimal("100.00"),
        snapshot_price=Decimal("50.00"),
        snapshot_value=Decimal("5000.00"),
    )
    db.add(holding)
    db.commit()

    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "_SF:abc12345"
    assert data[0]["security_name"] == "Vanguard Target Retirement 2045"


def test_get_account_holdings_includes_market_values(client: object, account, holding, db):
    """Test that holdings include market_price and market_value from DHV."""
    acct_snap = db.query(AccountSnapshot).filter(
        AccountSnapshot.account_id == account.id
    ).first()
    security = get_or_create_security(db, "AAPL")
    _create_dhv(
        db, account.id, acct_snap.id, security,
        valuation_date=date.today(),
        quantity=Decimal("10.00"),
        close_price=Decimal("175.00"),
        market_value=Decimal("1750.00"),
    )

    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert Decimal(data[0]["market_price"]) == Decimal("175.00")
    assert Decimal(data[0]["market_value"]) == Decimal("1750.00")
    # Snapshot values should still be present
    assert Decimal(data[0]["snapshot_price"]) == Decimal("150.50")
    assert Decimal(data[0]["snapshot_value"]) == Decimal("1505.00")


def test_get_account_holdings_market_values_null_without_dhv(client: object, account, holding, db):
    """Test that market_price and market_value are null when no DHV data exists."""
    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["market_price"] is None
    assert data[0]["market_value"] is None


# --- Manual Account Tests ---


@pytest.fixture
def manual_account(client, db):
    """Create a manual account via the API."""
    response = client.post(
        "/api/accounts/manual",
        json={"name": "My House"},
    )
    assert response.status_code == 200
    return response.json()


def test_create_manual_account(client):
    response = client.post(
        "/api/accounts/manual",
        json={"name": "Real Estate"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["provider_name"] == "Manual"
    assert data["name"] == "Real Estate"
    assert data["is_active"] is True


def test_create_manual_account_with_institution(client):
    response = client.post(
        "/api/accounts/manual",
        json={"name": "Savings", "institution_name": "Local Bank"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["institution_name"] == "Local Bank"


def test_add_holding_to_manual_account(client, manual_account):
    account_id = manual_account["id"]
    response = client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"ticker": "HOME", "quantity": "1", "market_value": "500000"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "HOME"
    assert Decimal(data["snapshot_value"]) == Decimal("500000")


def test_add_holding_to_synced_account_rejected(client, account):
    response = client.post(
        f"/api/accounts/{account.id}/holdings",
        json={"ticker": "AAPL", "quantity": "10", "market_value": "1500"},
    )
    assert response.status_code == 400
    assert "manual accounts" in response.json()["detail"].lower()


def test_update_holding(client, manual_account):
    account_id = manual_account["id"]

    # Add a holding first
    add_resp = client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"ticker": "HOME", "quantity": "1", "market_value": "500000"},
    )
    holding_id = add_resp.json()["id"]

    # Update it
    response = client.put(
        f"/api/accounts/{account_id}/holdings/{holding_id}",
        json={"ticker": "HOME", "quantity": "1", "market_value": "520000"},
    )
    assert response.status_code == 200
    data = response.json()
    assert Decimal(data["snapshot_value"]) == Decimal("520000")


def test_update_holding_not_found(client, manual_account):
    account_id = manual_account["id"]

    # Add a holding so the account has a snapshot
    client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"ticker": "HOME", "quantity": "1", "market_value": "500000"},
    )

    response = client.put(
        f"/api/accounts/{account_id}/holdings/nonexistent-id",
        json={"ticker": "HOME", "quantity": "1", "market_value": "520000"},
    )
    assert response.status_code == 404


def test_update_holding_on_synced_account_rejected(client, account):
    response = client.put(
        f"/api/accounts/{account.id}/holdings/some-id",
        json={"ticker": "AAPL", "quantity": "10", "market_value": "1500"},
    )
    assert response.status_code == 400


def test_delete_holding(client, manual_account):
    account_id = manual_account["id"]

    add_resp = client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"ticker": "HOME", "quantity": "1", "market_value": "500000"},
    )
    holding_id = add_resp.json()["id"]

    response = client.delete(
        f"/api/accounts/{account_id}/holdings/{holding_id}",
    )
    assert response.status_code == 204


def test_delete_holding_not_found(client, manual_account):
    account_id = manual_account["id"]

    # Add a holding so the account has a snapshot
    client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"ticker": "HOME", "quantity": "1", "market_value": "500000"},
    )

    response = client.delete(
        f"/api/accounts/{account_id}/holdings/nonexistent-id",
    )
    assert response.status_code == 404


def test_delete_holding_on_synced_account_rejected(client, account):
    response = client.delete(
        f"/api/accounts/{account.id}/holdings/some-id",
    )
    assert response.status_code == 400


def test_add_holding_creates_lot_api(client, manual_account):
    account_id = manual_account["id"]
    response = client.post(
        f"/api/accounts/{account_id}/holdings",
        json={
            "ticker": "AAPL",
            "quantity": "10",
            "price": "150",
            "market_value": "1500",
            "acquisition_date": "2024-01-15",
            "cost_basis_per_unit": "120",
        },
    )
    assert response.status_code == 200

    # Verify the lot was created via the lots API
    lots_resp = client.get(f"/api/accounts/{account_id}/lots")
    assert lots_resp.status_code == 200
    lots = lots_resp.json()
    assert len(lots) == 1
    lot = lots[0]
    assert lot["ticker"] == "AAPL"
    assert lot["acquisition_date"] == "2024-01-15"
    assert Decimal(lot["cost_basis_per_unit"]) == Decimal("120")
    assert Decimal(lot["original_quantity"]) == Decimal("10")
    assert lot["source"] == "manual"


def test_holdings_appear_in_get_holdings(client, manual_account):
    account_id = manual_account["id"]
    client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"ticker": "HOME", "quantity": "1", "market_value": "500000"},
    )

    response = client.get(f"/api/accounts/{account_id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "HOME"


def test_manual_account_appears_in_list_with_value(client, manual_account):
    account_id = manual_account["id"]
    client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"ticker": "HOME", "quantity": "1", "market_value": "500000"},
    )

    response = client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    manual = [a for a in data if a["id"] == account_id]
    assert len(manual) == 1
    assert Decimal(manual[0]["value"]) == Decimal("500000")


# --- Other Mode (description-based) Holding Tests ---


def test_add_other_holding_via_api(client, manual_account):
    account_id = manual_account["id"]
    response = client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"description": "Primary Residence", "market_value": "500000"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"].startswith("_MAN:")
    assert Decimal(data["snapshot_value"]) == Decimal("500000")


def test_add_other_holding_returns_security_name(client, manual_account):
    account_id = manual_account["id"]
    client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"description": "Primary Residence", "market_value": "500000"},
    )

    response = client.get(f"/api/accounts/{account_id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["security_name"] == "Primary Residence"


def test_update_other_holding_via_api(client, manual_account):
    account_id = manual_account["id"]

    # Add other holding
    add_resp = client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"description": "Primary Residence", "market_value": "500000"},
    )
    holding_id = add_resp.json()["id"]

    # Update it
    response = client.put(
        f"/api/accounts/{account_id}/holdings/{holding_id}",
        json={"description": "Primary Residence", "market_value": "520000"},
    )
    assert response.status_code == 200
    data = response.json()
    assert Decimal(data["snapshot_value"]) == Decimal("520000")
    assert data["ticker"].startswith("_MAN:")


def test_other_holding_visible_in_holdings_list(client, manual_account):
    account_id = manual_account["id"]

    # Add a security holding and an other holding
    client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"ticker": "VTI", "quantity": "100", "market_value": "25000"},
    )
    client.post(
        f"/api/accounts/{account_id}/holdings",
        json={"description": "Primary Residence", "market_value": "500000"},
    )

    response = client.get(f"/api/accounts/{account_id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    tickers = {h["ticker"] for h in data}
    assert "VTI" in tickers
    assert any(t.startswith("_MAN:") for t in tickers)


# --- Account Type and Include in Allocation Tests ---


def test_update_account_type(client: object, account):
    """Test updating account_type field."""
    response = client.patch(
        f"/api/accounts/{account.id}",
        json={"account_type": "roth_ira"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["account_type"] == "roth_ira"


def test_update_account_type_invalid(client: object, account):
    """Test that invalid account_type returns 422."""
    response = client.patch(
        f"/api/accounts/{account.id}",
        json={"account_type": "invalid_type"},
    )
    assert response.status_code == 422


def test_update_include_in_allocation(client: object, account):
    """Test updating include_in_allocation field."""
    response = client.patch(
        f"/api/accounts/{account.id}",
        json={"include_in_allocation": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["include_in_allocation"] is False


def test_new_fields_in_list_response(client: object, account):
    """Test that list accounts includes account_type and include_in_allocation."""
    response = client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "account_type" in data[0]
    assert "include_in_allocation" in data[0]
    assert data[0]["include_in_allocation"] is True
    assert data[0]["account_type"] is None


def test_new_fields_in_get_response(client: object, account):
    """Test that get account includes account_type and include_in_allocation."""
    response = client.get(f"/api/accounts/{account.id}")
    assert response.status_code == 200
    data = response.json()
    assert "account_type" in data
    assert "include_in_allocation" in data
    assert data["include_in_allocation"] is True


# --- Delete Account Tests ---


def test_delete_account(client: object, account):
    """Test deleting an account returns 204."""
    response = client.delete(f"/api/accounts/{account.id}")
    assert response.status_code == 204

    # Verify account is gone
    response = client.get(f"/api/accounts/{account.id}")
    assert response.status_code == 404


def test_delete_account_not_found(client: object):
    """Test deleting non-existent account returns 404."""
    response = client.delete("/api/accounts/nonexistent-id")
    assert response.status_code == 404


def test_delete_account_cascades_holdings(client: object, account, holding, db):
    """Test deleting account cascades to holdings."""
    # The holding fixture includes account_snapshot with market_value of 1505.00
    response = client.delete(f"/api/accounts/{account.id}")
    assert response.status_code == 204

    # Verify holdings are gone
    remaining = db.query(Holding).join(AccountSnapshot).filter(AccountSnapshot.account_id == account.id).count()
    assert remaining == 0


def test_delete_account_cascades_activities(client: object, account, activity, db):
    """Test deleting account cascades to activities."""
    response = client.delete(f"/api/accounts/{account.id}")
    assert response.status_code == 204

    # Verify activities are gone
    from models.activity import Activity
    remaining = db.query(Activity).filter(Activity.account_id == account.id).count()
    assert remaining == 0


def test_delete_account_cascades_account_snapshots(client: object, account, sync_session, db):
    """Test deleting account cascades to account snapshots."""
    _create_account_snapshot(db, account.id, sync_session.id, Decimal("1505.00"))

    response = client.delete(f"/api/accounts/{account.id}")
    assert response.status_code == 204

    # Verify account snapshots are gone
    remaining = db.query(AccountSnapshot).filter(AccountSnapshot.account_id == account.id).count()
    assert remaining == 0


# --- Cost Basis Enrichment Tests ---


def test_holdings_include_cost_basis_when_lots_exist(client, account, holding, db):
    """Test that holdings response includes cost basis fields when lots exist."""
    security = get_or_create_security(db, "AAPL")

    # Create DHV so we get market_price for unrealized gain/loss
    acct_snap = db.query(AccountSnapshot).filter(
        AccountSnapshot.account_id == account.id
    ).first()
    _create_dhv(
        db, account.id, acct_snap.id, security,
        valuation_date=date.today(),
        quantity=Decimal("10.00"),
        close_price=Decimal("175.00"),
        market_value=Decimal("1750.00"),
    )

    # Create a holding lot for this security
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        acquisition_date=date(2025, 1, 15),
        cost_basis_per_unit=Decimal("150.00"),
        original_quantity=Decimal("10.00"),
        current_quantity=Decimal("10.00"),
        is_closed=False,
        source="manual",
    )
    db.add(lot)
    db.commit()

    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    h = data[0]
    # cost_basis = 10 * 150 = 1500
    assert Decimal(h["cost_basis"]) == Decimal("1500.00")
    # gain_loss = (175 * 10) - 1500 = 250
    assert Decimal(h["gain_loss"]) == Decimal("250.00")
    # gain_loss_percent = 250 / 1500
    assert abs(float(h["gain_loss_percent"]) - 250 / 1500) < 0.001
    # lot_coverage = 10 / 10 = 1.0
    assert Decimal(h["lot_coverage"]) == Decimal("1")
    assert h["lot_count"] == 1
    assert Decimal(h["realized_gain_loss"]) == Decimal("0")


def test_holdings_cost_basis_null_when_no_lots(client, account, holding, db):
    """Test that cost basis fields are null when no lots exist (backward compatible)."""
    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    h = data[0]
    assert h["cost_basis"] is None
    assert h["gain_loss"] is None
    assert h["gain_loss_percent"] is None
    assert h["lot_coverage"] is None
    assert h["lot_count"] is None
    assert h["realized_gain_loss"] is None


def test_holdings_partial_lot_coverage(client, account, holding, db):
    """Test partial lot coverage when lot quantity < holding quantity."""
    security = get_or_create_security(db, "AAPL")

    # Create a lot covering only 6 of 10 shares
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        acquisition_date=date(2025, 1, 15),
        cost_basis_per_unit=Decimal("150.00"),
        original_quantity=Decimal("6.00"),
        current_quantity=Decimal("6.00"),
        is_closed=False,
        source="manual",
    )
    db.add(lot)
    db.commit()

    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    h = data[0]
    # lot_coverage = 6 / 10 = 0.6
    assert abs(float(h["lot_coverage"]) - 0.6) < 0.001
    assert h["lot_count"] == 1
    assert Decimal(h["cost_basis"]) == Decimal("900.00")


def test_holdings_realized_gain_loss_with_disposals(client, account, holding, db):
    """Test realized gain/loss is computed from lot disposals."""
    security = get_or_create_security(db, "AAPL")

    # Create a lot with a disposal
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        acquisition_date=date(2025, 1, 15),
        cost_basis_per_unit=Decimal("150.00"),
        original_quantity=Decimal("15.00"),
        current_quantity=Decimal("10.00"),
        is_closed=False,
        source="manual",
    )
    db.add(lot)
    db.flush()

    # Disposal: sold 5 shares at $180, cost was $150 → gain = 5 * (180 - 150) = 150
    disposal = LotDisposal(
        holding_lot_id=lot.id,
        account_id=account.id,
        security_id=security.id,
        disposal_date=date(2025, 6, 15),
        quantity=Decimal("5.00"),
        proceeds_per_unit=Decimal("180.00"),
        source="manual",
    )
    db.add(disposal)
    db.commit()

    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    h = data[0]
    assert Decimal(h["realized_gain_loss"]) == Decimal("150.00")
    assert h["lot_count"] == 1


def test_holdings_cost_basis_without_dhv(client, account, holding, db):
    """Test cost basis populated but gain_loss null when no DHV data."""
    security = get_or_create_security(db, "AAPL")

    # No DHV created — market_price will be None
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        acquisition_date=date(2025, 1, 15),
        cost_basis_per_unit=Decimal("150.00"),
        original_quantity=Decimal("10.00"),
        current_quantity=Decimal("10.00"),
        is_closed=False,
        source="manual",
    )
    db.add(lot)
    db.commit()

    response = client.get(f"/api/accounts/{account.id}/holdings")
    assert response.status_code == 200
    data = response.json()
    h = data[0]
    assert Decimal(h["cost_basis"]) == Decimal("1500.00")
    assert h["gain_loss"] is None
    assert h["gain_loss_percent"] is None
    assert h["lot_count"] == 1
