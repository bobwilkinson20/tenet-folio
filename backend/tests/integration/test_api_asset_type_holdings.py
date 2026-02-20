"""Integration tests for asset type holdings API endpoint."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from models import Account, AccountSnapshot, AssetClass, DailyHoldingValue, Holding, Security, SyncSession
from tests.fixtures import get_or_create_security


def _create_holding_with_account_snapshot(
    db, sync_session, account, security, ticker, quantity, price, market_value, acct_snap=None
):
    """Create an AccountSnapshot (if not provided), a Holding, and a DailyHoldingValue."""
    if acct_snap is None:
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

    dhv = DailyHoldingValue(
        valuation_date=date.today(),
        account_id=account.id,
        account_snapshot_id=acct_snap.id,
        security_id=security.id,
        ticker=ticker,
        quantity=quantity,
        close_price=price,
        market_value=market_value,
    )
    db.add(dhv)

    return acct_snap, holding


class TestAssetTypeHoldingsAPI:
    """Integration tests for GET /api/asset-types/{id}/holdings."""

    def test_returns_holdings_for_valid_asset_type(self, client: TestClient, db):
        """Returns holdings classified under an asset type."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="Test Account",
            assigned_asset_class=asset_type,
        )
        sync_session = SyncSession(is_complete=True)
        db.add_all([asset_type, account, sync_session])
        db.flush()

        security = get_or_create_security(db, "AAPL")
        acct_snap, holding = _create_holding_with_account_snapshot(
            db, sync_session, account, security, "AAPL",
            Decimal("10"), Decimal("150.00"), Decimal("1500.00")
        )
        db.commit()

        response = client.get(f"/api/asset-types/{asset_type.id}/holdings")
        assert response.status_code == 200

        data = response.json()
        assert data["asset_type_id"] == asset_type.id
        assert data["asset_type_name"] == "Stocks"
        assert data["asset_type_color"] == "#3B82F6"
        assert data["total_value"] == "1500.00"
        assert len(data["holdings"]) == 1

        h = data["holdings"][0]
        assert h["holding_id"]  # DHV id, just verify it exists
        assert h["account_id"] == account.id
        assert h["account_name"] == "Test Account"
        assert h["ticker"] == "AAPL"
        assert h["market_value"] == "1500.00"

    def test_returns_404_for_nonexistent_asset_type(self, client: TestClient):
        """Returns 404 for an asset type that doesn't exist."""
        response = client.get("/api/asset-types/nonexistent-id/holdings")
        assert response.status_code == 404

    def test_returns_unassigned_holdings(self, client: TestClient, db):
        """Returns unclassified holdings when asset_type_id is 'unassigned'."""
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="Test Account",
        )
        sync_session = SyncSession(is_complete=True)
        db.add_all([account, sync_session])
        db.flush()

        security = get_or_create_security(db, "MYSTERY")
        _create_holding_with_account_snapshot(
            db, sync_session, account, security, "MYSTERY",
            Decimal("100"), Decimal("10.00"), Decimal("1000.00")
        )
        db.commit()

        response = client.get("/api/asset-types/unassigned/holdings")
        assert response.status_code == 200

        data = response.json()
        assert data["asset_type_id"] == "unassigned"
        assert data["asset_type_name"] == "Unknown"
        assert data["asset_type_color"] == "#9CA3AF"
        assert len(data["holdings"]) == 1
        assert data["holdings"][0]["ticker"] == "MYSTERY"

    def test_returns_empty_when_no_sync_session(self, client: TestClient, db):
        """Returns empty holdings when no sync_session exists."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        response = client.get(f"/api/asset-types/{asset_type.id}/holdings")
        assert response.status_code == 200

        data = response.json()
        assert data["total_value"] == "0.00"
        assert data["holdings"] == []

    def test_includes_account_and_security_names(self, client: TestClient, db):
        """Response includes account names and security names."""
        asset_type = AssetClass(name="Bonds", color="#10B981")
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="My Brokerage",
        )
        security = Security(
            ticker="BND",
            name="Vanguard Total Bond Market ETF",
            manual_asset_class=asset_type,
        )
        sync_session = SyncSession(is_complete=True)
        db.add_all([asset_type, account, security, sync_session])
        db.flush()

        _create_holding_with_account_snapshot(
            db, sync_session, account, security, "BND",
            Decimal("50"), Decimal("80.00"), Decimal("4000.00")
        )
        db.commit()

        response = client.get(f"/api/asset-types/{asset_type.id}/holdings")
        assert response.status_code == 200

        data = response.json()
        h = data["holdings"][0]
        assert h["account_name"] == "My Brokerage"
        assert h["security_name"] == "Vanguard Total Bond Market ETF"

    def test_total_value_sums_correctly(self, client: TestClient, db):
        """Total value is the sum of all holdings' market values."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="Test Account",
            assigned_asset_class=asset_type,
        )
        sync_session = SyncSession(is_complete=True)
        db.add_all([asset_type, account, sync_session])
        db.flush()

        # Create account snapshot with total value of both holdings
        acct_snap = AccountSnapshot(
            account_id=account.id,
            sync_session_id=sync_session.id,
            status="success",
            total_value=Decimal("2000.00"),
        )
        db.add(acct_snap)
        db.flush()

        sec_aapl = get_or_create_security(db, "AAPL")
        sec_googl = get_or_create_security(db, "GOOGL")
        _create_holding_with_account_snapshot(
            db, sync_session, account, sec_aapl, "AAPL",
            Decimal("10"), Decimal("150.00"), Decimal("1500.00"),
            acct_snap=acct_snap
        )
        _create_holding_with_account_snapshot(
            db, sync_session, account, sec_googl, "GOOGL",
            Decimal("5"), Decimal("100.00"), Decimal("500.00"),
            acct_snap=acct_snap
        )
        db.commit()

        response = client.get(f"/api/asset-types/{asset_type.id}/holdings")
        assert response.status_code == 200

        data = response.json()
        assert data["total_value"] == "2000.00"
        assert len(data["holdings"]) == 2
