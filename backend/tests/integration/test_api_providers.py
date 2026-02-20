"""Integration tests for the providers API."""

from models import Account
from services.provider_service import ProviderService


class TestListProviders:
    """Tests for GET /api/providers."""

    def test_returns_all_providers(self, client):
        """Returns all 5 known providers."""
        response = client.get("/api/providers")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 5
        names = [p["name"] for p in data]
        assert "SnapTrade" in names
        assert "SimpleFIN" in names
        assert "IBKR" in names
        assert "Coinbase" in names
        assert "Schwab" in names

    def test_default_enabled(self, client):
        """All providers are enabled by default."""
        response = client.get("/api/providers")
        data = response.json()
        for provider in data:
            assert provider["is_enabled"] is True

    def test_has_credentials_from_registry(self, client):
        """Shows has_credentials based on the mock registry (SnapTrade configured)."""
        response = client.get("/api/providers")
        data = response.json()
        by_name = {p["name"]: p for p in data}

        # client fixture has MockProviderRegistry with SnapTrade
        assert by_name["SnapTrade"]["has_credentials"] is True
        assert by_name["SimpleFIN"]["has_credentials"] is False

    def test_shows_account_count(self, client, db):
        """Shows account counts per provider."""
        db.add(Account(provider_name="SnapTrade", external_id="a1", name="A1", is_active=True))
        db.add(Account(provider_name="SnapTrade", external_id="a2", name="A2", is_active=True))
        db.commit()

        response = client.get("/api/providers")
        data = response.json()
        by_name = {p["name"]: p for p in data}
        assert by_name["SnapTrade"]["account_count"] == 2


class TestUpdateProvider:
    """Tests for PUT /api/providers/{name}."""

    def test_disable_provider(self, client):
        """Disabling a provider returns updated status."""
        response = client.put(
            "/api/providers/SnapTrade",
            json={"is_enabled": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "SnapTrade"
        assert data["is_enabled"] is False

    def test_enable_provider(self, client, db):
        """Re-enabling a disabled provider works."""
        ProviderService.set_enabled(db, "SnapTrade", False)

        response = client.put(
            "/api/providers/SnapTrade",
            json={"is_enabled": True},
        )
        assert response.status_code == 200
        assert response.json()["is_enabled"] is True

    def test_unknown_provider_404(self, client):
        """Unknown provider name returns 404."""
        response = client.put(
            "/api/providers/FakeProvider",
            json={"is_enabled": True},
        )
        assert response.status_code == 404

    def test_toggle_persists(self, client, db):
        """Disabled state persists across GET calls."""
        client.put("/api/providers/SimpleFIN", json={"is_enabled": False})

        response = client.get("/api/providers")
        data = response.json()
        by_name = {p["name"]: p for p in data}
        assert by_name["SimpleFIN"]["is_enabled"] is False
        assert by_name["SnapTrade"]["is_enabled"] is True  # others unaffected


class TestSyncRespectsDisabled:
    """Tests that sync skips disabled providers."""

    def test_disabled_provider_skipped_during_sync(self, client_with_mock_sync, db):
        """A disabled provider is not synced."""
        ProviderService.set_enabled(db, "SnapTrade", False)

        response = client_with_mock_sync.post("/api/sync")
        assert response.status_code == 200

        data = response.json()
        # With the only provider disabled, no accounts should be synced
        assert data["is_complete"] is False

        # No accounts should have been created
        accounts = db.query(Account).all()
        assert len(accounts) == 0

    def test_enabled_provider_syncs_normally(self, client_with_mock_sync, db):
        """Enabled providers sync as usual."""
        # SnapTrade is enabled by default (no row)
        response = client_with_mock_sync.post("/api/sync")
        assert response.status_code == 200

        data = response.json()
        assert data["is_complete"] is True

        # Accounts should have been created
        accounts = db.query(Account).all()
        assert len(accounts) > 0
