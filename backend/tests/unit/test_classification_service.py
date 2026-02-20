"""Tests for ClassificationService."""

import pytest
from decimal import Decimal

from models import AssetClass, Security, Account
from services.classification_service import ClassificationService


class TestClassificationService:
    """Tests for ClassificationService."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return ClassificationService()

    @pytest.fixture
    def asset_types(self, db):
        """Create test asset types."""
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
        bonds = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
        db.add_all([stocks, bonds])
        db.commit()
        return {"stocks": stocks, "bonds": bonds}

    def test_get_holding_asset_type_account_override(self, service, db, asset_types):
        """Test classification uses account override first."""
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="Test Account",
            assigned_asset_class=asset_types["stocks"],
        )
        security = Security(ticker="AAPL", manual_asset_class=asset_types["bonds"])
        db.add_all([account, security])
        db.commit()

        # Account override should take precedence
        result = service.get_holding_asset_type(db, account.id, "AAPL")
        assert result.id == asset_types["stocks"].id

    def test_get_holding_asset_type_security_assignment(self, service, db, asset_types):
        """Test classification falls back to security assignment."""
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="Test Account",
        )
        security = Security(ticker="AAPL", manual_asset_class=asset_types["bonds"])
        db.add_all([account, security])
        db.commit()

        # Should use security assignment
        result = service.get_holding_asset_type(db, account.id, "AAPL")
        assert result.id == asset_types["bonds"].id

    def test_get_holding_asset_type_unknown(self, service, db):
        """Test classification returns None for unclassified holdings."""
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="Test Account",
        )
        db.add(account)
        db.commit()

        # No security or account assignment
        result = service.get_holding_asset_type(db, account.id, "AAPL")
        assert result is None


class TestClassifyHoldingsBatch:
    """Tests for ClassificationService.classify_holdings_batch."""

    @pytest.fixture
    def service(self):
        return ClassificationService()

    @pytest.fixture
    def asset_types(self, db):
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
        bonds = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
        db.add_all([stocks, bonds])
        db.commit()
        return {"stocks": stocks, "bonds": bonds}

    def test_classify_holdings_batch_account_override(self, service, db, asset_types):
        """Account-level classification wins over security assignment."""
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="Test Account",
            assigned_asset_class=asset_types["stocks"],
        )
        security = Security(ticker="AAPL", manual_asset_class=asset_types["bonds"])
        db.add_all([account, security])
        db.commit()

        result = service.classify_holdings_batch(db, [(account.id, "AAPL")])

        assert result[(account.id, "AAPL")].id == asset_types["stocks"].id

    def test_classify_holdings_batch_security_assignment(self, service, db, asset_types):
        """Falls back to security assignment when no account override."""
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="Test Account",
        )
        security = Security(ticker="AAPL", manual_asset_class=asset_types["bonds"])
        db.add_all([account, security])
        db.commit()

        result = service.classify_holdings_batch(db, [(account.id, "AAPL")])

        assert result[(account.id, "AAPL")].id == asset_types["bonds"].id

    def test_classify_holdings_batch_mixed(self, service, db, asset_types):
        """Some classified, some unclassified."""
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="Test Account",
        )
        security = Security(ticker="AAPL", manual_asset_class=asset_types["stocks"])
        db.add_all([account, security])
        db.commit()

        result = service.classify_holdings_batch(
            db, [(account.id, "AAPL"), (account.id, "UNKNOWN")]
        )

        assert result[(account.id, "AAPL")].id == asset_types["stocks"].id
        assert result[(account.id, "UNKNOWN")] is None

    def test_classify_holdings_batch_empty(self, service, db):
        """Empty input returns empty dict."""
        result = service.classify_holdings_batch(db, [])

        assert result == {}
