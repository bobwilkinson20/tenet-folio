"""Tests for report_service.generate_account_asset_class_rows."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from models import Account, AssetClass, Security
from services.portfolio_service import CurrentHolding
from services.report_service import generate_account_asset_class_rows
from tests.fixtures import create_sync_session_with_holdings


class TestGenerateAccountAssetClassRows:
    """Tests for generate_account_asset_class_rows."""

    def test_empty_portfolio(self, db):
        """Returns empty list when no holdings exist."""
        rows = generate_account_asset_class_rows(db)
        assert rows == []

    def test_single_account_single_class(self, db):
        """Single account with one classified holding."""
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("100.00"))
        db.add(stocks)
        db.flush()

        account = Account(
            provider_name="Test", external_id="a1", name="Brokerage", is_active=True
        )
        db.add(account)
        db.flush()

        db.add(Security(ticker="AAPL", name="Apple", manual_asset_class=stocks))
        db.flush()

        create_sync_session_with_holdings(
            db, account,
            datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("1500.00"))],
        )
        db.commit()

        rows = generate_account_asset_class_rows(db)
        assert len(rows) == 1
        assert rows[0] == ["Brokerage", "Stocks", "1500.00"]

    def test_single_account_multiple_classes(self, db):
        """Single account with multiple asset classes, sorted by class name."""
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
        bonds = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
        db.add_all([stocks, bonds])
        db.flush()

        account = Account(
            provider_name="Test", external_id="a1", name="Brokerage", is_active=True
        )
        db.add(account)
        db.flush()

        db.add(Security(ticker="AAPL", name="Apple", manual_asset_class=stocks))
        db.add(Security(ticker="BND", name="Bond Fund", manual_asset_class=bonds))
        db.flush()

        create_sync_session_with_holdings(
            db, account,
            datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("1500.00")), ("BND", Decimal("500.00"))],
        )
        db.commit()

        rows = generate_account_asset_class_rows(db)
        assert len(rows) == 2
        # First row has account name, sorted by asset class
        assert rows[0] == ["Brokerage", "Bonds", "500.00"]
        assert rows[1] == ["/", "Stocks", "1500.00"]

    def test_multiple_accounts(self, db):
        """Multiple accounts sorted by account name."""
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("100.00"))
        db.add(stocks)
        db.flush()

        acct_a = Account(
            provider_name="Test", external_id="a1", name="Alpha Account", is_active=True
        )
        acct_b = Account(
            provider_name="Test", external_id="a2", name="Beta Account", is_active=True
        )
        db.add_all([acct_a, acct_b])
        db.flush()

        db.add(Security(ticker="AAPL", name="Apple", manual_asset_class=stocks))
        db.add(Security(ticker="GOOG", name="Google", manual_asset_class=stocks))
        db.flush()

        ts = datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc)
        create_sync_session_with_holdings(
            db, acct_a, ts, [("AAPL", Decimal("1000.00"))]
        )
        create_sync_session_with_holdings(
            db, acct_b, ts, [("GOOG", Decimal("2000.00"))]
        )
        db.commit()

        rows = generate_account_asset_class_rows(db)
        assert len(rows) == 2
        assert rows[0][0] == "Alpha Account"
        assert rows[1][0] == "Beta Account"

    def test_aggregation_same_class(self, db):
        """Multiple holdings in same class are aggregated."""
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("100.00"))
        db.add(stocks)
        db.flush()

        account = Account(
            provider_name="Test", external_id="a1", name="Brokerage", is_active=True
        )
        db.add(account)
        db.flush()

        db.add(Security(ticker="AAPL", name="Apple", manual_asset_class=stocks))
        db.add(Security(ticker="GOOG", name="Google", manual_asset_class=stocks))
        db.flush()

        create_sync_session_with_holdings(
            db, account,
            datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("1000.00")), ("GOOG", Decimal("2000.00"))],
        )
        db.commit()

        rows = generate_account_asset_class_rows(db)
        assert len(rows) == 1
        assert rows[0] == ["Brokerage", "Stocks", "3000.00"]

    def test_continuation_marker(self, db):
        """Second row for same account uses / as continuation."""
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
        bonds = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
        db.add_all([stocks, bonds])
        db.flush()

        account = Account(
            provider_name="Test", external_id="a1", name="My Account", is_active=True
        )
        db.add(account)
        db.flush()

        db.add(Security(ticker="AAPL", name="Apple", manual_asset_class=stocks))
        db.add(Security(ticker="BND", name="Bond Fund", manual_asset_class=bonds))
        db.flush()

        create_sync_session_with_holdings(
            db, account,
            datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("1500.00")), ("BND", Decimal("500.00"))],
        )
        db.commit()

        rows = generate_account_asset_class_rows(db)
        assert rows[0][0] == "My Account"
        assert rows[1][0] == "/"

    def test_unclassified_holdings(self, db):
        """Holdings without classification appear as 'Unclassified'."""
        account = Account(
            provider_name="Test", external_id="a1", name="Brokerage", is_active=True
        )
        db.add(account)
        db.flush()

        # No asset class assigned to security
        db.add(Security(ticker="XYZ", name="Unknown Corp"))
        db.flush()

        create_sync_session_with_holdings(
            db, account,
            datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc),
            [("XYZ", Decimal("750.00"))],
        )
        db.commit()

        rows = generate_account_asset_class_rows(db)
        assert len(rows) == 1
        assert rows[0] == ["Brokerage", "Unclassified", "750.00"]

    def test_values_are_numeric_strings(self, db):
        """Market values are formatted as 2-decimal numeric strings."""
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("100.00"))
        db.add(stocks)
        db.flush()

        account = Account(
            provider_name="Test", external_id="a1", name="Account", is_active=True
        )
        db.add(account)
        db.flush()

        db.add(Security(ticker="AAPL", name="Apple", manual_asset_class=stocks))
        db.flush()

        create_sync_session_with_holdings(
            db, account,
            datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("1234.50"))],
        )
        db.commit()

        rows = generate_account_asset_class_rows(db)
        assert rows[0][2] == "1234.50"

    def test_none_market_value_skipped(self, db):
        """Holdings with None market_value are silently skipped."""
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("100.00"))
        db.add(stocks)
        db.flush()

        account = Account(
            provider_name="Test", external_id="a1", name="Brokerage", is_active=True
        )
        db.add(account)
        db.flush()

        db.add(Security(ticker="AAPL", name="Apple", manual_asset_class=stocks))
        db.add(Security(ticker="XYZ", name="No Price"))
        db.flush()

        holdings = [
            CurrentHolding(account_id=account.id, ticker="AAPL", market_value=Decimal("1000.00")),
            CurrentHolding(account_id=account.id, ticker="XYZ", market_value=None),
        ]

        with patch(
            "services.report_service.PortfolioService"
        ) as mock_ps_cls:
            mock_ps_cls.return_value.get_current_holdings.return_value = holdings
            rows = generate_account_asset_class_rows(db)

        assert len(rows) == 1
        assert rows[0] == ["Brokerage", "Stocks", "1000.00"]

    def test_zero_balance_sentinel_excluded(self, db):
        """_ZERO_BALANCE sentinel holdings are excluded from report rows."""
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("100.00"))
        db.add(stocks)
        db.flush()

        account = Account(
            provider_name="Test", external_id="a1", name="Brokerage", is_active=True
        )
        db.add(account)
        db.flush()

        db.add(Security(ticker="AAPL", name="Apple", manual_asset_class=stocks))
        db.flush()

        holdings = [
            CurrentHolding(account_id=account.id, ticker="AAPL", market_value=Decimal("1000.00")),
            CurrentHolding(account_id=account.id, ticker="_ZERO_BALANCE", market_value=Decimal("0")),
        ]

        with patch(
            "services.report_service.PortfolioService"
        ) as mock_ps_cls:
            mock_ps_cls.return_value.get_current_holdings.return_value = holdings
            rows = generate_account_asset_class_rows(db)

        assert len(rows) == 1
        assert rows[0] == ["Brokerage", "Stocks", "1000.00"]

    def test_allocation_only_forwarded(self, db):
        """allocation_only=True is forwarded to PortfolioService."""
        with patch(
            "services.report_service.PortfolioService"
        ) as mock_ps_cls:
            mock_ps_cls.return_value.get_current_holdings.return_value = []
            generate_account_asset_class_rows(db, allocation_only=True)

            mock_ps_cls.return_value.get_current_holdings.assert_called_once_with(
                db, allocation_only=True
            )
