"""Integration tests for asset types API endpoints."""

from fastapi.testclient import TestClient

from models import AssetClass, Security
from decimal import Decimal


class TestAssetTypesAPI:
    """Integration tests for /api/asset-types endpoints."""

    def test_list_asset_types_empty(self, client: TestClient):
        """Test listing asset types when empty."""
        response = client.get("/api/asset-types")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total_target_percent"] == "0.00"

    def test_list_asset_types_with_data(self, client: TestClient, db):
        """Test listing asset types with data."""
        type1 = AssetClass(name="US Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
        type2 = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
        db.add_all([type1, type2])
        db.commit()

        response = client.get("/api/asset-types")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total_target_percent"] == "100.00"

    def test_get_asset_type(self, client: TestClient, db):
        """Test getting specific asset type."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        response = client.get(f"/api/asset-types/{asset_type.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "US Stocks"
        assert data["color"] == "#3B82F6"
        assert data["security_count"] == 0
        assert data["account_count"] == 0

    def test_get_asset_type_not_found(self, client: TestClient):
        """Test getting non-existent asset type."""
        response = client.get("/api/asset-types/nonexistent")
        assert response.status_code == 404

    def test_create_asset_type(self, client: TestClient):
        """Test creating new asset type."""
        response = client.post(
            "/api/asset-types",
            json={"name": "US Stocks", "color": "#3B82F6"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "US Stocks"
        assert data["color"] == "#3B82F6"
        assert "id" in data

    def test_create_asset_type_duplicate_name(self, client: TestClient, db):
        """Test creating asset type with duplicate name fails."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        response = client.post(
            "/api/asset-types",
            json={"name": "US Stocks", "color": "#10B981"},
        )
        assert response.status_code == 400

    def test_update_asset_type(self, client: TestClient, db):
        """Test updating asset type."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        response = client.patch(
            f"/api/asset-types/{asset_type.id}",
            json={"name": "US Equities", "color": "#F59E0B"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "US Equities"
        assert data["color"] == "#F59E0B"

    def test_update_asset_type_partial(self, client: TestClient, db):
        """Test partial update of asset type."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        response = client.patch(
            f"/api/asset-types/{asset_type.id}",
            json={"name": "US Equities"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "US Equities"
        assert data["color"] == "#3B82F6"  # Unchanged

    def test_delete_asset_type(self, client: TestClient, db):
        """Test deleting asset type."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()
        type_id = asset_type.id

        response = client.delete(f"/api/asset-types/{type_id}")
        assert response.status_code == 204

        # Verify deleted
        response = client.get(f"/api/asset-types/{type_id}")
        assert response.status_code == 404

    def test_delete_asset_type_with_assignments(self, client: TestClient, db):
        """Test deleting asset type with assignments fails."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        security = Security(ticker="AAPL", manual_asset_class=asset_type)
        db.add_all([asset_type, security])
        db.commit()

        response = client.delete(f"/api/asset-types/{asset_type.id}")
        assert response.status_code == 400
        assert "assigned" in response.json()["detail"].lower()
