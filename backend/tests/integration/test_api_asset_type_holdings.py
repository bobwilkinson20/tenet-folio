"""Integration tests for asset type holdings API endpoint."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from models import Account, AccountSnapshot, AssetClass, DailyHoldingValue, Holding, HoldingLot, Security, SyncSession
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

    def test_holdings_without_lots_return_null_cost_basis(self, client: TestClient, db):
        """Holdings without HoldingLot records have null lot fields."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        account = Account(
            provider_name="Test",
            external_id="test-no-lots",
            name="No Lots Account",
            assigned_asset_class=asset_type,
        )
        sync_session = SyncSession(is_complete=True)
        db.add_all([asset_type, account, sync_session])
        db.flush()

        security = get_or_create_security(db, "MSFT")
        _create_holding_with_account_snapshot(
            db, sync_session, account, security, "MSFT",
            Decimal("20"), Decimal("400.00"), Decimal("8000.00")
        )
        db.commit()

        response = client.get(f"/api/asset-types/{asset_type.id}/holdings")
        assert response.status_code == 200

        h = response.json()["holdings"][0]
        assert h["cost_basis"] is None
        assert h["gain_loss"] is None
        assert h["gain_loss_percent"] is None
        assert h["lot_coverage"] is None
        assert h["lot_count"] is None

    def test_holdings_with_lots_include_cost_basis(self, client: TestClient, db):
        """Holdings with HoldingLot records include cost basis data."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        account = Account(
            provider_name="Test",
            external_id="test-with-lots",
            name="Lots Account",
            assigned_asset_class=asset_type,
        )
        sync_session = SyncSession(is_complete=True)
        db.add_all([asset_type, account, sync_session])
        db.flush()

        security = get_or_create_security(db, "AAPL")
        # Holding: 10 shares at $200 = $2000 market value
        _create_holding_with_account_snapshot(
            db, sync_session, account, security, "AAPL",
            Decimal("10"), Decimal("200.00"), Decimal("2000.00")
        )

        # Lot: bought 10 shares at $150 = $1500 cost basis
        lot = HoldingLot(
            account_id=account.id,
            security_id=security.id,
            ticker="AAPL",
            acquisition_date=date(2025, 1, 15),
            cost_basis_per_unit=Decimal("150.00"),
            original_quantity=Decimal("10"),
            current_quantity=Decimal("10"),
            source="manual",
        )
        db.add(lot)
        db.commit()

        response = client.get(f"/api/asset-types/{asset_type.id}/holdings")
        assert response.status_code == 200

        h = response.json()["holdings"][0]
        assert Decimal(h["cost_basis"]) == Decimal("1500.00")
        assert Decimal(h["gain_loss"]) == Decimal("500.00")  # 2000 - 1500
        assert h["gain_loss_percent"] is not None
        assert float(h["gain_loss_percent"]) > 0
        assert Decimal(h["lot_coverage"]) == Decimal("1")
        assert h["lot_count"] == 1

    def test_cross_account_lot_data_independent(self, client: TestClient, db):
        """Lot data from one account doesn't bleed into another."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        acct1 = Account(
            provider_name="Test", external_id="acct-1", name="Account With Lots",
            assigned_asset_class=asset_type,
        )
        acct2 = Account(
            provider_name="Test", external_id="acct-2", name="Account Without Lots",
            assigned_asset_class=asset_type,
        )
        sync_session = SyncSession(is_complete=True)
        db.add_all([asset_type, acct1, acct2, sync_session])
        db.flush()

        security = get_or_create_security(db, "VTI")

        # Both accounts hold VTI
        _create_holding_with_account_snapshot(
            db, sync_session, acct1, security, "VTI",
            Decimal("10"), Decimal("250.00"), Decimal("2500.00")
        )
        _create_holding_with_account_snapshot(
            db, sync_session, acct2, security, "VTI",
            Decimal("5"), Decimal("250.00"), Decimal("1250.00")
        )

        # Only acct1 has a lot
        lot = HoldingLot(
            account_id=acct1.id,
            security_id=security.id,
            ticker="VTI",
            acquisition_date=date(2025, 3, 1),
            cost_basis_per_unit=Decimal("200.00"),
            original_quantity=Decimal("10"),
            current_quantity=Decimal("10"),
            source="manual",
        )
        db.add(lot)
        db.commit()

        response = client.get(f"/api/asset-types/{asset_type.id}/holdings")
        assert response.status_code == 200

        holdings = response.json()["holdings"]
        assert len(holdings) == 2

        by_account = {h["account_name"]: h for h in holdings}
        assert by_account["Account With Lots"]["lot_count"] == 1
        assert by_account["Account With Lots"]["cost_basis"] is not None
        assert by_account["Account Without Lots"]["lot_count"] is None
        assert by_account["Account Without Lots"]["cost_basis"] is None

    def test_partial_lot_coverage(self, client: TestClient, db):
        """Lot covering partial quantity shows correct lot_coverage fraction."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        account = Account(
            provider_name="Test", external_id="test-partial", name="Partial Lots",
            assigned_asset_class=asset_type,
        )
        sync_session = SyncSession(is_complete=True)
        db.add_all([asset_type, account, sync_session])
        db.flush()

        security = get_or_create_security(db, "TSLA")
        # Holding: 20 shares
        _create_holding_with_account_snapshot(
            db, sync_session, account, security, "TSLA",
            Decimal("20"), Decimal("300.00"), Decimal("6000.00")
        )

        # Lot: only 10 shares tracked (50% coverage)
        lot = HoldingLot(
            account_id=account.id,
            security_id=security.id,
            ticker="TSLA",
            acquisition_date=date(2025, 2, 1),
            cost_basis_per_unit=Decimal("250.00"),
            original_quantity=Decimal("10"),
            current_quantity=Decimal("10"),
            source="manual",
        )
        db.add(lot)
        db.commit()

        response = client.get(f"/api/asset-types/{asset_type.id}/holdings")
        assert response.status_code == 200

        h = response.json()["holdings"][0]
        assert h["lot_count"] == 1
        assert Decimal(h["lot_coverage"]) == Decimal("0.5")
