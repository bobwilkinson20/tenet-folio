"""Integration tests for securities API endpoints."""

from fastapi.testclient import TestClient

from models import AssetClass, Security


class TestSecuritiesAPI:
    """Integration tests for /api/securities endpoints."""

    def test_list_securities_empty(self, client: TestClient):
        """Test listing securities when empty."""
        response = client.get("/api/securities")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_securities_with_data(self, client: TestClient, db):
        """Test listing securities with data."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        sec1 = Security(ticker="AAPL", name="Apple Inc.", manual_asset_class=asset_type)
        sec2 = Security(ticker="GOOGL", name="Alphabet Inc.")
        db.add_all([asset_type, sec1, sec2])
        db.commit()

        response = client.get("/api/securities")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Check assigned security
        aapl = next(s for s in data if s["ticker"] == "AAPL")
        assert aapl["name"] == "Apple Inc."
        assert aapl["asset_type_name"] == "Stocks"
        assert aapl["asset_type_color"] == "#3B82F6"

        # Check unassigned security
        googl = next(s for s in data if s["ticker"] == "GOOGL")
        assert googl["asset_type_name"] is None

    def test_list_securities_search(self, client: TestClient, db):
        """Test searching securities by ticker."""
        sec1 = Security(ticker="AAPL", name="Apple Inc.")
        sec2 = Security(ticker="GOOGL", name="Alphabet Inc.")
        db.add_all([sec1, sec2])
        db.commit()

        response = client.get("/api/securities?search=AAP")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"

    def test_list_securities_unassigned_only(self, client: TestClient, db):
        """Test filtering unassigned securities."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        sec1 = Security(ticker="AAPL", manual_asset_class=asset_type)
        sec2 = Security(ticker="GOOGL")
        db.add_all([asset_type, sec1, sec2])
        db.commit()

        response = client.get("/api/securities?unassigned_only=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "GOOGL"

    def test_get_unassigned_count(self, client: TestClient, db):
        """Test getting unassigned securities count."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        sec1 = Security(ticker="AAPL", manual_asset_class=asset_type)
        sec2 = Security(ticker="GOOGL")
        sec3 = Security(ticker="MSFT")
        db.add_all([asset_type, sec1, sec2, sec3])
        db.commit()

        response = client.get("/api/securities/unassigned")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2

    def test_update_security_type(self, client: TestClient, db):
        """Test assigning asset type to security."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        security = Security(ticker="AAPL")
        db.add_all([asset_type, security])
        db.commit()

        response = client.patch(
            f"/api/securities/{security.id}",
            json={"manual_asset_class_id": asset_type.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["manual_asset_class_id"] == asset_type.id

    def test_update_security_unassign_type(self, client: TestClient, db):
        """Test unassigning asset type from security."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        security = Security(ticker="AAPL", manual_asset_class=asset_type)
        db.add_all([asset_type, security])
        db.commit()

        response = client.patch(
            f"/api/securities/{security.id}",
            json={"manual_asset_class_id": None},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["manual_asset_class_id"] is None

    def test_update_security_not_found(self, client: TestClient):
        """Test updating non-existent security."""
        response = client.patch(
            "/api/securities/nonexistent",
            json={"manual_asset_class_id": None},
        )
        assert response.status_code == 404

    def test_update_security_invalid_type(self, client: TestClient, db):
        """Test assigning non-existent asset type is allowed (foreign key will be null)."""
        security = Security(ticker="AAPL")
        db.add(security)
        db.commit()

        response = client.patch(
            f"/api/securities/{security.id}",
            json={"manual_asset_class_id": "nonexistent"},
        )
        # Doesn't validate - foreign key constraint not enforced in code
        assert response.status_code == 200

    def test_zero_balance_hidden_from_list(self, client: TestClient, db):
        """_ZERO_BALANCE sentinel security is hidden from the securities list."""
        sec1 = Security(ticker="AAPL", name="Apple Inc.")
        sec2 = Security(ticker="_ZERO_BALANCE", name="Zero Balance Sentinel")
        db.add_all([sec1, sec2])
        db.commit()

        response = client.get("/api/securities")
        assert response.status_code == 200
        data = response.json()
        tickers = [s["ticker"] for s in data]
        assert "AAPL" in tickers
        assert "_ZERO_BALANCE" not in tickers

    def test_zero_balance_hidden_from_unassigned(self, client: TestClient, db):
        """_ZERO_BALANCE sentinel security is hidden from unassigned count."""
        sec1 = Security(ticker="AAPL")
        sec2 = Security(ticker="_ZERO_BALANCE", name="Zero Balance Sentinel")
        db.add_all([sec1, sec2])
        db.commit()

        response = client.get("/api/securities/unassigned")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        tickers = [s["ticker"] for s in data["items"]]
        assert "_ZERO_BALANCE" not in tickers
