"""Integration tests for Plaid API endpoints."""

import pytest
from fastapi.testclient import TestClient

from api.plaid import _get_plaid_client
from main import app
from models.plaid_item import PlaidItem
from tests.fixtures.mocks import MockPlaidClient


@pytest.fixture
def mock_plaid_client():
    """Create a mock Plaid client."""
    return MockPlaidClient()


@pytest.fixture
def plaid_client(db, mock_plaid_client):
    """Create a test client with mocked Plaid dependency."""
    from database import get_db

    def override_get_db():
        try:
            yield db
        finally:
            pass

    def override_get_plaid_client():
        return mock_plaid_client

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_get_plaid_client] = override_get_plaid_client
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestCreateLinkToken:
    def test_creates_link_token(self, plaid_client):
        response = plaid_client.post("/api/plaid/link-token")
        assert response.status_code == 200
        data = response.json()
        assert "link_token" in data
        assert data["link_token"] == "link-sandbox-test-token"

    def test_returns_400_when_not_configured(self, db):
        """Returns 400 when Plaid is not configured."""
        from database import get_db

        unconfigured = MockPlaidClient(should_fail=True)

        def override_get_db():
            try:
                yield db
            finally:
                pass

        def override_get_plaid_client():
            return unconfigured

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[_get_plaid_client] = override_get_plaid_client
        client = TestClient(app)

        response = client.post("/api/plaid/link-token")
        assert response.status_code == 400

        app.dependency_overrides.clear()


class TestExchangeToken:
    def test_exchanges_token_and_creates_item(self, plaid_client, db):
        response = plaid_client.post(
            "/api/plaid/exchange-token",
            json={
                "public_token": "public-sandbox-test",
                "institution_id": "ins_001",
                "institution_name": "Chase",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["item_id"] == "item-sandbox-test"
        assert data["institution_name"] == "Chase"

        # Verify DB persistence
        item = db.query(PlaidItem).filter(PlaidItem.item_id == "item-sandbox-test").first()
        assert item is not None
        assert item.access_token == "access-sandbox-test"
        assert item.institution_name == "Chase"
        assert item.institution_id == "ins_001"

    def test_upserts_existing_item(self, plaid_client, db):
        """Re-linking same institution updates existing item."""
        # Create first item
        plaid_client.post(
            "/api/plaid/exchange-token",
            json={"public_token": "public-1", "institution_name": "Chase"},
        )

        # Exchange again (same item_id from mock)
        plaid_client.post(
            "/api/plaid/exchange-token",
            json={"public_token": "public-2", "institution_name": "Chase Updated"},
        )

        items = db.query(PlaidItem).all()
        assert len(items) == 1
        assert items[0].institution_name == "Chase Updated"


class TestListItems:
    def test_lists_items(self, plaid_client, db):
        # Create a few items
        db.add(PlaidItem(
            item_id="item-1",
            access_token="access-1",
            institution_id="ins_1",
            institution_name="Chase",
        ))
        db.add(PlaidItem(
            item_id="item-2",
            access_token="access-2",
            institution_name="Vanguard",
        ))
        db.commit()

        response = plaid_client.get("/api/plaid/items")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [d["institution_name"] for d in data]
        assert "Chase" in names
        assert "Vanguard" in names

    def test_lists_empty(self, plaid_client):
        response = plaid_client.get("/api/plaid/items")
        assert response.status_code == 200
        assert response.json() == []


class TestRemoveItem:
    def test_removes_item(self, plaid_client, db):
        db.add(PlaidItem(
            item_id="item-to-delete",
            access_token="access-delete",
            institution_name="OldBank",
        ))
        db.commit()

        response = plaid_client.delete("/api/plaid/items/item-to-delete")
        assert response.status_code == 200
        assert response.json()["item_id"] == "item-to-delete"

        # Verify deleted
        item = db.query(PlaidItem).filter(PlaidItem.item_id == "item-to-delete").first()
        assert item is None

    def test_returns_404_for_unknown_item(self, plaid_client):
        response = plaid_client.delete("/api/plaid/items/nonexistent")
        assert response.status_code == 404
