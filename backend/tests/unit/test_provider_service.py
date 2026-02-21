"""Tests for ProviderService."""

import pytest

from models import Account
from models.provider_setting import ProviderSetting
from services.provider_service import ALL_PROVIDER_NAMES, ProviderService
from tests.fixtures.mocks import MockProviderRegistry, MockSnapTradeClient


class TestListProviders:
    """Tests for ProviderService.list_providers."""

    def test_returns_all_six_providers(self, db):
        """Returns all known providers even with no data."""
        result = ProviderService.list_providers(db)
        names = [p.name for p in result]
        assert names == ALL_PROVIDER_NAMES
        assert len(result) == 6

    def test_default_enabled(self, db):
        """All providers are enabled by default (no rows)."""
        result = ProviderService.list_providers(db)
        for p in result:
            assert p.is_enabled is True

    def test_has_credentials_without_registry(self, db):
        """Without a registry, all has_credentials are False."""
        result = ProviderService.list_providers(db)
        for p in result:
            assert p.has_credentials is False

    def test_has_credentials_with_registry(self, db):
        """Registry shows which providers have credentials."""
        mock_client = MockSnapTradeClient()
        registry = MockProviderRegistry({"SnapTrade": mock_client})

        result = ProviderService.list_providers(db, registry=registry)
        by_name = {p.name: p for p in result}

        assert by_name["SnapTrade"].has_credentials is True
        assert by_name["SimpleFIN"].has_credentials is False
        assert by_name["IBKR"].has_credentials is False

    def test_disabled_provider_shown(self, db):
        """Disabled providers are listed with is_enabled=False."""
        ProviderService.set_enabled(db, "SnapTrade", False)

        result = ProviderService.list_providers(db)
        by_name = {p.name: p for p in result}
        assert by_name["SnapTrade"].is_enabled is False
        assert by_name["SimpleFIN"].is_enabled is True  # default

    def test_account_count(self, db):
        """Shows account counts per provider."""
        db.add(Account(provider_name="SnapTrade", external_id="a1", name="A1", is_active=True))
        db.add(Account(provider_name="SnapTrade", external_id="a2", name="A2", is_active=True))
        db.add(Account(provider_name="SimpleFIN", external_id="b1", name="B1", is_active=True))
        db.add(Account(provider_name="SimpleFIN", external_id="b2", name="B2", is_active=False))
        db.commit()

        result = ProviderService.list_providers(db)
        by_name = {p.name: p for p in result}
        assert by_name["SnapTrade"].account_count == 2
        assert by_name["SimpleFIN"].account_count == 1  # inactive excluded
        assert by_name["IBKR"].account_count == 0

    def test_last_sync_time(self, db):
        """Shows last sync time from most recent account sync."""
        from datetime import datetime, timezone

        acc = Account(
            provider_name="SnapTrade",
            external_id="a1",
            name="A1",
            is_active=True,
            last_sync_time=datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        )
        db.add(acc)
        db.commit()

        result = ProviderService.list_providers(db)
        by_name = {p.name: p for p in result}
        assert by_name["SnapTrade"].last_sync_time is not None
        assert by_name["SimpleFIN"].last_sync_time is None


class TestSetEnabled:
    """Tests for ProviderService.set_enabled."""

    def test_creates_row(self, db):
        """Creates a ProviderSetting row if none exists."""
        ProviderService.set_enabled(db, "SnapTrade", False)

        setting = db.query(ProviderSetting).filter_by(provider_name="SnapTrade").first()
        assert setting is not None
        assert setting.is_enabled is False

    def test_updates_existing_row(self, db):
        """Updates an existing ProviderSetting row."""
        ProviderService.set_enabled(db, "SnapTrade", False)
        ProviderService.set_enabled(db, "SnapTrade", True)

        settings = db.query(ProviderSetting).filter_by(provider_name="SnapTrade").all()
        assert len(settings) == 1
        assert settings[0].is_enabled is True

    def test_rejects_unknown_provider(self, db):
        """Raises ValueError for unknown provider names."""
        with pytest.raises(ValueError, match="Unknown provider"):
            ProviderService.set_enabled(db, "FakeProvider", True)


class TestIsProviderEnabled:
    """Tests for ProviderService.is_provider_enabled."""

    def test_no_row_returns_true(self, db):
        """Returns True when no ProviderSetting row exists (backwards compat)."""
        assert ProviderService.is_provider_enabled(db, "SnapTrade") is True

    def test_enabled_row(self, db):
        """Returns True when is_enabled=True."""
        ProviderService.set_enabled(db, "SnapTrade", True)
        assert ProviderService.is_provider_enabled(db, "SnapTrade") is True

    def test_disabled_row(self, db):
        """Returns False when is_enabled=False."""
        ProviderService.set_enabled(db, "SnapTrade", False)
        assert ProviderService.is_provider_enabled(db, "SnapTrade") is False
