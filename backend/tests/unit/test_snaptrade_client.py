"""Unit tests for SnapTradeClient provider protocol implementation."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from integrations.snaptrade_client import (
    SnapTradeAccount,
    SnapTradeClient,
    SnapTradeHolding,
)
from integrations.provider_protocol import ProviderAccount, ProviderHolding, ProviderSyncResult


# Mock settings with empty defaults to avoid picking up real .env values
@pytest.fixture
def mock_empty_settings():
    """Fixture that mocks settings with empty credential values."""
    with patch("integrations.snaptrade_client.settings") as mock_settings:
        mock_settings.SNAPTRADE_CLIENT_ID = ""
        mock_settings.SNAPTRADE_CONSUMER_KEY = ""
        mock_settings.SNAPTRADE_USER_ID = ""
        mock_settings.SNAPTRADE_USER_SECRET = ""
        yield mock_settings


class TestSnapTradeClientProviderProtocol:
    """Tests for SnapTradeClient's ProviderClient protocol implementation."""

    def test_provider_name(self):
        """SnapTradeClient returns correct provider name."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        assert client.provider_name == "SnapTrade"

    def test_is_configured_true(self):
        """is_configured returns True when all credentials present."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        assert client.is_configured() is True

    def test_is_configured_false_missing_user_id(self, mock_empty_settings):
        """is_configured returns False when user_id missing."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="",  # Empty - will fall back to mocked empty settings
                user_secret="test_secret",
            )

        assert client.is_configured() is False

    def test_is_configured_false_missing_user_secret(self, mock_empty_settings):
        """is_configured returns False when user_secret missing."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="",  # Empty - will fall back to mocked empty settings
            )

        assert client.is_configured() is False

    def test_is_configured_false_missing_client_id(self, mock_empty_settings):
        """is_configured returns False when client_id missing."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="",  # Empty - will fall back to mocked empty settings
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        assert client.is_configured() is False

    def test_is_configured_false_missing_consumer_key(self, mock_empty_settings):
        """is_configured returns False when consumer_key missing."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="",  # Empty - will fall back to mocked empty settings
                user_id="test_user",
                user_secret="test_secret",
            )

        assert client.is_configured() is False

    def test_get_provider_accounts_maps_correctly(self):
        """get_provider_accounts maps SnapTradeAccount to ProviderAccount."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        # Mock get_accounts to return SnapTradeAccount objects
        client.get_accounts = MagicMock(
            return_value=[
                SnapTradeAccount(
                    id="acc1",
                    name="Brokerage Account",
                    brokerage_name="Fidelity",
                    account_number="XXX-1234",
                ),
                SnapTradeAccount(
                    id="acc2",
                    name="IRA Account",
                    brokerage_name="Vanguard",
                    account_number=None,
                ),
            ]
        )

        result = client.get_provider_accounts()

        assert len(result) == 2
        assert isinstance(result[0], ProviderAccount)
        assert result[0].id == "acc1"
        assert result[0].name == "Brokerage Account"
        assert result[0].institution == "Fidelity"
        assert result[0].account_number == "XXX-1234"

        assert result[1].id == "acc2"
        assert result[1].institution == "Vanguard"
        assert result[1].account_number is None

    def test_get_holdings_maps_correctly(self):
        """get_holdings maps SnapTradeHolding to ProviderHolding."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        # Mock get_all_holdings to return SnapTradeHolding objects
        client.get_all_holdings = MagicMock(
            return_value=[
                SnapTradeHolding(
                    account_id="acc1",
                    symbol="AAPL",
                    quantity=10.5,
                    price=150.25,
                    market_value=1577.625,
                    currency="USD",
                ),
                SnapTradeHolding(
                    account_id="acc1",
                    symbol="GOOGL",
                    quantity=5.0,
                    price=140.0,
                    market_value=700.0,
                    currency="USD",
                ),
            ]
        )

        result = client.get_holdings()

        assert len(result) == 2
        assert isinstance(result[0], ProviderHolding)
        assert result[0].account_id == "acc1"
        assert result[0].symbol == "AAPL"
        assert result[0].quantity == Decimal("10.5")
        assert result[0].price == Decimal("150.25")
        assert result[0].market_value == Decimal("1577.625")
        assert result[0].currency == "USD"
        assert result[0].name is None  # SnapTrade doesn't provide security name
        assert result[0].cost_basis is None  # No average_purchase_price set
        assert result[0].raw_data is None  # No raw_data set

    def test_get_holdings_maps_cost_basis(self):
        """get_holdings maps average_purchase_price to cost_basis."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        client.get_all_holdings = MagicMock(
            return_value=[
                SnapTradeHolding(
                    account_id="acc1",
                    symbol="AAPL",
                    quantity=10.0,
                    price=175.00,
                    market_value=1750.00,
                    currency="USD",
                    average_purchase_price=145.50,
                    raw_data={"symbol": "AAPL", "units": 10},
                ),
            ]
        )

        result = client.get_holdings()

        assert len(result) == 1
        assert result[0].cost_basis == Decimal("145.5")
        assert result[0].raw_data == {"symbol": "AAPL", "units": 10}

    def test_get_holdings_zero_cost_basis_treated_as_none(self):
        """Zero average_purchase_price is treated as None."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        client.get_all_holdings = MagicMock(
            return_value=[
                SnapTradeHolding(
                    account_id="acc1",
                    symbol="BTC",
                    quantity=0.5,
                    price=60000.0,
                    market_value=30000.0,
                    currency="USD",
                    average_purchase_price=0.0,
                ),
            ]
        )

        result = client.get_holdings()

        assert result[0].cost_basis is None

    def test_get_holdings_filtered_by_account(self):
        """get_holdings with account_id filters to that account."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        # Mock _get_holdings_for_account
        client._get_holdings_for_account = MagicMock(
            return_value=[
                SnapTradeHolding(
                    account_id="acc1",
                    symbol="AAPL",
                    quantity=10.0,
                    price=150.0,
                    market_value=1500.0,
                    currency="USD",
                ),
            ]
        )

        result = client.get_holdings(account_id="acc1")

        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        client._get_holdings_for_account.assert_called_once_with("acc1")

    def test_sync_all_extracts_last_successful_sync(self):
        """sync_all() extracts last_successful_sync from account sync_status."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        # Mock the SDK list_user_accounts to return raw account with sync_status
        mock_accounts_response = [
            {
                "id": "acc1",
                "name": "Brokerage",
                "institution_name": "Fidelity",
                "sync_status": {
                    "holdings": {
                        "initial_sync_completed": True,
                        "last_successful_sync": "2024-06-28 18:42:46.561408+00:00",
                    },
                },
            },
        ]
        client.client.account_information.list_user_accounts = MagicMock(
            return_value=mock_accounts_response
        )

        # Mock get_holdings for the position data
        client.get_holdings = MagicMock(
            return_value=[
                ProviderHolding(
                    account_id="acc1",
                    symbol="AAPL",
                    quantity=Decimal("10"),
                    price=Decimal("150"),
                    market_value=Decimal("1500"),
                    currency="USD",
                    name=None,
                ),
            ]
        )

        result = client.sync_all()

        assert isinstance(result, ProviderSyncResult)
        assert len(result.holdings) == 1
        assert result.holdings[0].symbol == "AAPL"
        assert result.errors == []
        assert "acc1" in result.balance_dates
        assert result.balance_dates["acc1"] is not None
        assert result.balance_dates["acc1"].year == 2024
        assert result.balance_dates["acc1"].month == 6

    def test_sync_all_handles_missing_sync_status(self):
        """sync_all() handles accounts without sync_status."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        # Account with no sync_status
        mock_accounts_response = [
            {
                "id": "acc1",
                "name": "Brokerage",
                "institution_name": "Fidelity",
            },
        ]
        client.client.account_information.list_user_accounts = MagicMock(
            return_value=mock_accounts_response
        )
        client.get_holdings = MagicMock(return_value=[])

        result = client.sync_all()

        assert result.balance_dates["acc1"] is None

    def test_sync_all_handles_null_last_successful_sync(self):
        """sync_all() handles sync_status.holdings with null last_successful_sync."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        mock_accounts_response = [
            {
                "id": "acc1",
                "name": "Brokerage",
                "institution_name": "Fidelity",
                "sync_status": {
                    "holdings": {
                        "initial_sync_completed": False,
                        "last_successful_sync": None,
                    },
                },
            },
        ]
        client.client.account_information.list_user_accounts = MagicMock(
            return_value=mock_accounts_response
        )
        client.get_holdings = MagicMock(return_value=[])

        result = client.sync_all()

        assert result.balance_dates["acc1"] is None

    def test_extract_last_successful_sync_with_object_attrs(self):
        """_extract_last_successful_sync works with SDK objects (attribute access)."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        # Simulate SDK object with nested attributes
        class HoldingsMeta:
            initial_sync_completed = True
            last_successful_sync = "2024-06-28 18:42:46.561408+00:00"

        class SyncStatus:
            holdings = HoldingsMeta()

        class AccountObj:
            sync_status = SyncStatus()

        result = client._extract_last_successful_sync(AccountObj())

        assert result is not None
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 28

    def test_get_holdings_decimal_conversion(self):
        """get_holdings converts float to Decimal correctly."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        # Test with floating point values that could cause precision issues
        client.get_all_holdings = MagicMock(
            return_value=[
                SnapTradeHolding(
                    account_id="acc1",
                    symbol="BTC",
                    quantity=0.00123456,
                    price=45678.90,
                    market_value=56.357894284,
                    currency="USD",
                ),
            ]
        )

        result = client.get_holdings()

        # Verify Decimal conversion preserves precision
        assert isinstance(result[0].quantity, Decimal)
        assert isinstance(result[0].price, Decimal)
        assert isinstance(result[0].market_value, Decimal)


class TestSnapTradeCostBasisExtraction:
    """Tests for SnapTrade cost basis extraction from holdings API response."""

    def test_cost_basis_from_dict_response(self):
        """average_purchase_price is extracted from dict-format position."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        mock_response = {
            "positions": [
                {
                    "symbol": {"symbol": "AAPL", "currency": {"code": "USD"}},
                    "units": 10,
                    "price": 175.0,
                    "average_purchase_price": 145.50,
                },
            ],
            "balances": [],
        }

        client.client.account_information.get_user_holdings = MagicMock(
            return_value=mock_response
        )

        holdings = client._get_holdings_for_account("acc1")

        assert len(holdings) == 1
        assert holdings[0].average_purchase_price == 145.50
        assert holdings[0].raw_data is not None

    def test_cost_basis_none_when_missing(self):
        """average_purchase_price is None when not in position data."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        mock_response = {
            "positions": [
                {
                    "symbol": {"symbol": "VTI", "currency": {"code": "USD"}},
                    "units": 50,
                    "price": 220.0,
                },
            ],
            "balances": [],
        }

        client.client.account_information.get_user_holdings = MagicMock(
            return_value=mock_response
        )

        holdings = client._get_holdings_for_account("acc1")

        assert len(holdings) == 1
        assert holdings[0].average_purchase_price is None

    def test_cost_basis_from_sdk_object(self):
        """average_purchase_price is extracted from SDK object (attribute access)."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        class CurrencyObj:
            code = "USD"

        class SymbolObj:
            symbol = "MSFT"
            currency = CurrencyObj()

        class PositionObj:
            symbol = SymbolObj()
            units = 25
            price = 380.0
            average_purchase_price = 320.75

        class ResponseObj:
            positions = [PositionObj()]
            balances = []

        response_obj = ResponseObj()
        response_obj.body = response_obj

        client.client.account_information.get_user_holdings = MagicMock(
            return_value=response_obj
        )

        holdings = client._get_holdings_for_account("acc1")

        assert len(holdings) == 1
        assert holdings[0].average_purchase_price == 320.75

    def test_cost_basis_maps_to_provider_holding(self):
        """average_purchase_price flows through to ProviderHolding.cost_basis."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        mock_response = {
            "positions": [
                {
                    "symbol": {"symbol": "AAPL", "currency": {"code": "USD"}},
                    "units": 10,
                    "price": 175.0,
                    "average_purchase_price": 145.50,
                },
            ],
            "balances": [],
        }

        client.client.account_information.get_user_holdings = MagicMock(
            return_value=mock_response
        )

        result = client.get_holdings(account_id="acc1")

        assert len(result) == 1
        assert result[0].cost_basis == Decimal("145.5")
        assert result[0].raw_data is not None


class TestSnapTradeCashExtraction:
    """Tests for SnapTrade cash balance extraction from holdings API response."""

    def test_cash_extracted_from_dict_response(self):
        """Cash balances are extracted from dict-format API response."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        mock_response = {
            "positions": [
                {
                    "symbol": {"symbol": "AAPL", "currency": {"code": "USD"}},
                    "units": 10,
                    "price": 150.0,
                },
            ],
            "balances": [
                {
                    "currency": {"code": "USD"},
                    "cash": 5000.50,
                },
            ],
        }

        client.client.account_information.get_user_holdings = MagicMock(
            return_value=mock_response
        )

        holdings = client._get_holdings_for_account("acc1")

        assert len(holdings) == 2
        cash = next(h for h in holdings if h.symbol == "_CASH:USD")
        assert cash.quantity == 5000.50
        assert cash.price == 1.0
        assert cash.market_value == 5000.50
        assert cash.currency == "USD"

    def test_multiple_currency_cash_balances(self):
        """Multiple currency cash balances each create separate holdings."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        mock_response = {
            "positions": [],
            "balances": [
                {"currency": {"code": "USD"}, "cash": 3000.00},
                {"currency": {"code": "CAD"}, "cash": 1500.00},
            ],
        }

        client.client.account_information.get_user_holdings = MagicMock(
            return_value=mock_response
        )

        holdings = client._get_holdings_for_account("acc1")

        assert len(holdings) == 2
        symbols = {h.symbol for h in holdings}
        assert symbols == {"_CASH:USD", "_CASH:CAD"}

        usd_cash = next(h for h in holdings if h.symbol == "_CASH:USD")
        assert usd_cash.market_value == 3000.00

        cad_cash = next(h for h in holdings if h.symbol == "_CASH:CAD")
        assert cad_cash.market_value == 1500.00
        assert cad_cash.currency == "CAD"

    def test_zero_cash_balance_skipped(self):
        """Zero cash balances are not included."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        mock_response = {
            "positions": [],
            "balances": [
                {"currency": {"code": "USD"}, "cash": 0},
                {"currency": {"code": "CAD"}, "cash": 500.00},
            ],
        }

        client.client.account_information.get_user_holdings = MagicMock(
            return_value=mock_response
        )

        holdings = client._get_holdings_for_account("acc1")

        assert len(holdings) == 1
        assert holdings[0].symbol == "_CASH:CAD"

    def test_missing_balances_array(self):
        """Response without balances array still returns positions."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        mock_response = {
            "positions": [
                {
                    "symbol": {"symbol": "VTI", "currency": {"code": "USD"}},
                    "units": 50,
                    "price": 220.0,
                },
            ],
        }

        client.client.account_information.get_user_holdings = MagicMock(
            return_value=mock_response
        )

        holdings = client._get_holdings_for_account("acc1")

        assert len(holdings) == 1
        assert holdings[0].symbol == "VTI"

    def test_cash_from_sdk_object_attributes(self):
        """Cash extraction works with SDK objects (attribute access)."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        class CurrencyObj:
            code = "USD"

        class BalanceObj:
            currency = CurrencyObj()
            cash = 2500.00

        class ResponseObj:
            positions = []
            balances = [BalanceObj()]

        response_obj = ResponseObj()
        # SDK responses have a .body attribute that returns self
        response_obj.body = response_obj

        client.client.account_information.get_user_holdings = MagicMock(
            return_value=response_obj
        )

        holdings = client._get_holdings_for_account("acc1")

        assert len(holdings) == 1
        assert holdings[0].symbol == "_CASH:USD"
        assert holdings[0].market_value == 2500.00

    def test_cash_included_in_get_holdings(self):
        """Cash balances flow through get_holdings() to ProviderHolding."""
        with patch("integrations.snaptrade_client.SnapTrade"):
            client = SnapTradeClient(
                client_id="test_id",
                consumer_key="test_key",
                user_id="test_user",
                user_secret="test_secret",
            )

        mock_response = {
            "positions": [
                {
                    "symbol": {"symbol": "AAPL", "currency": {"code": "USD"}},
                    "units": 10,
                    "price": 150.0,
                },
            ],
            "balances": [
                {"currency": {"code": "USD"}, "cash": 1000.00},
            ],
        }

        client.client.account_information.get_user_holdings = MagicMock(
            return_value=mock_response
        )

        result = client.get_holdings(account_id="acc1")

        assert len(result) == 2
        cash = next(h for h in result if h.symbol == "_CASH:USD")
        assert isinstance(cash, ProviderHolding)
        assert cash.quantity == Decimal("1000.0")
        assert cash.price == Decimal("1.0")
        assert cash.market_value == Decimal("1000.0")
