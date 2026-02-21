"""Unit tests for PlaidClient provider protocol implementation."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from integrations.plaid_client import (
    PlaidClient,
    _generate_plaid_synthetic_symbol,
)
from integrations.provider_protocol import (
    ErrorCategory,
    ProviderSyncResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    """Fixture that mocks settings with configured Plaid credentials."""
    with patch("integrations.plaid_client.settings") as ms:
        ms.PLAID_CLIENT_ID = "test-client-id"
        ms.PLAID_SECRET = "test-secret"
        ms.PLAID_ENVIRONMENT = "sandbox"
        yield ms


@pytest.fixture
def mock_empty_settings():
    """Fixture that mocks settings with empty Plaid credentials."""
    with patch("integrations.plaid_client.settings") as ms:
        ms.PLAID_CLIENT_ID = ""
        ms.PLAID_SECRET = ""
        ms.PLAID_ENVIRONMENT = "sandbox"
        yield ms


@pytest.fixture
def mock_plaid_api():
    """Fixture that provides a mocked PlaidApi."""
    with patch("integrations.plaid_client.PlaidApi") as MockCls:
        api_instance = MagicMock()
        MockCls.return_value = api_instance
        yield api_instance


@pytest.fixture
def sample_holdings_response():
    """Sample investments_holdings_get response from Plaid."""
    return {
        "accounts": [
            {
                "account_id": "acc_001",
                "name": "My Brokerage",
                "official_name": "Brokerage Account",
                "mask": "1234",
                "balances": {
                    "current": 50000.00,
                    "iso_currency_code": "USD",
                },
            },
        ],
        "securities": [
            {
                "security_id": "sec_aapl",
                "ticker_symbol": "AAPL",
                "name": "Apple Inc.",
                "iso_currency_code": "USD",
            },
            {
                "security_id": "sec_fund",
                "ticker_symbol": None,
                "name": "Target Retirement 2045",
                "iso_currency_code": "USD",
            },
            {
                "security_id": "sec_cash",
                "ticker_symbol": "CUR:USD",
                "name": "US Dollar",
                "type": "cash",
                "is_cash_equivalent": True,
                "iso_currency_code": "USD",
            },
        ],
        "holdings": [
            {
                "account_id": "acc_001",
                "security_id": "sec_aapl",
                "quantity": 100,
                "institution_price": 150.50,
                "institution_value": 15050.00,
                "cost_basis": 14000.00,
                "iso_currency_code": "USD",
            },
            {
                "account_id": "acc_001",
                "security_id": "sec_fund",
                "quantity": 200,
                "institution_price": 50.00,
                "institution_value": 10000.00,
                "cost_basis": 9000.00,
                "iso_currency_code": "USD",
            },
            {
                "account_id": "acc_001",
                "security_id": "sec_cash",
                "quantity": 24950.00,
                "institution_price": 1.00,
                "institution_value": 24950.00,
                "iso_currency_code": "USD",
            },
        ],
    }


@pytest.fixture
def sample_transactions_response():
    """Sample investments_transactions_get response from Plaid."""
    return {
        "investment_transactions": [
            {
                "investment_transaction_id": "txn_001",
                "account_id": "acc_001",
                "security_id": "sec_aapl",
                "date": date(2026, 1, 15),
                "type": "buy",
                "subtype": "buy",
                "amount": 15050.00,  # Plaid: positive = cash outflow
                "quantity": 100,
                "price": 150.50,
                "fees": 5.00,
                "name": "Buy Apple",
                "iso_currency_code": "USD",
            },
            {
                "investment_transaction_id": "txn_002",
                "account_id": "acc_001",
                "security_id": "sec_aapl",
                "date": date(2026, 2, 1),
                "type": "sell",
                "subtype": "sell",
                "amount": -8000.00,  # Plaid: negative = cash inflow
                "quantity": -50,
                "price": 160.00,
                "fees": 5.00,
                "name": "Sell Apple",
                "iso_currency_code": "USD",
            },
            {
                "investment_transaction_id": "txn_003",
                "account_id": "acc_001",
                "security_id": "sec_aapl",
                "date": date(2026, 2, 5),
                "type": "cash",
                "subtype": "dividend",
                "amount": -25.50,
                "quantity": 0,
                "price": 0,
                "fees": 0,
                "name": "AAPL Dividend",
                "iso_currency_code": "USD",
            },
        ],
        "securities": [
            {
                "security_id": "sec_aapl",
                "ticker_symbol": "AAPL",
                "name": "Apple Inc.",
            },
        ],
        "total_investment_transactions": 3,
    }


# ---------------------------------------------------------------------------
# Tests: Configuration
# ---------------------------------------------------------------------------


class TestPlaidClientConfig:
    def test_is_configured_with_credentials(self, mock_settings):
        client = PlaidClient()
        assert client.is_configured() is True

    def test_is_not_configured_without_credentials(self, mock_empty_settings):
        client = PlaidClient()
        assert client.is_configured() is False

    def test_provider_name(self, mock_settings):
        client = PlaidClient()
        assert client.provider_name == "Plaid"


# ---------------------------------------------------------------------------
# Tests: Synthetic symbol generation
# ---------------------------------------------------------------------------


class TestSyntheticSymbol:
    def test_deterministic(self):
        """Same security_id always produces the same symbol."""
        s1 = _generate_plaid_synthetic_symbol("sec_12345")
        s2 = _generate_plaid_synthetic_symbol("sec_12345")
        assert s1 == s2

    def test_format(self):
        """Symbol has _PLAID:{8 hex chars} format."""
        symbol = _generate_plaid_synthetic_symbol("sec_abc")
        assert symbol.startswith("_PLAID:")
        assert len(symbol) == len("_PLAID:") + 8

    def test_different_ids_produce_different_symbols(self):
        s1 = _generate_plaid_synthetic_symbol("sec_aaa")
        s2 = _generate_plaid_synthetic_symbol("sec_bbb")
        assert s1 != s2


# ---------------------------------------------------------------------------
# Tests: Holding mapping
# ---------------------------------------------------------------------------


class TestMapHolding:
    def test_maps_holding_with_ticker(self, mock_settings, mock_plaid_api):
        client = PlaidClient()
        securities_map = {
            "sec_aapl": {
                "security_id": "sec_aapl",
                "ticker_symbol": "AAPL",
                "name": "Apple Inc.",
                "iso_currency_code": "USD",
            },
        }
        holding_data = {
            "account_id": "acc_001",
            "security_id": "sec_aapl",
            "quantity": 100,
            "institution_price": 150.50,
            "institution_value": 15050.00,
            "cost_basis": 14000.00,
            "iso_currency_code": "USD",
        }

        result = client._map_holding(holding_data, securities_map)

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.quantity == Decimal("100")
        assert result.price == Decimal("150.50")
        assert result.market_value == Decimal("15050.00")
        assert result.name == "Apple Inc."
        assert result.currency == "USD"
        # cost_basis = total / quantity = 14000 / 100 = 140
        assert result.cost_basis == Decimal("140")

    def test_maps_holding_without_ticker_to_synthetic(self, mock_settings, mock_plaid_api):
        client = PlaidClient()
        securities_map = {
            "sec_fund": {
                "security_id": "sec_fund",
                "ticker_symbol": None,
                "name": "Target Fund",
            },
        }
        holding_data = {
            "account_id": "acc_001",
            "security_id": "sec_fund",
            "quantity": 200,
            "institution_price": 50.00,
            "institution_value": 10000.00,
            "cost_basis": None,
            "iso_currency_code": "USD",
        }

        result = client._map_holding(holding_data, securities_map)

        assert result is not None
        assert result.symbol.startswith("_PLAID:")
        assert result.name == "Target Fund"
        assert result.cost_basis is None

    def test_skips_zero_quantity(self, mock_settings, mock_plaid_api):
        client = PlaidClient()
        holding_data = {
            "account_id": "acc_001",
            "security_id": "sec_aapl",
            "quantity": 0,
            "institution_price": 150.0,
            "institution_value": 0,
        }

        result = client._map_holding(holding_data, {})
        assert result is None


# ---------------------------------------------------------------------------
# Tests: Transaction mapping
# ---------------------------------------------------------------------------


class TestMapTransaction:
    def test_maps_buy_transaction(self, mock_settings, mock_plaid_api):
        """Buy: Plaid positive amount -> our negative amount."""
        client = PlaidClient()
        securities_map = {
            "sec_aapl": {"ticker_symbol": "AAPL", "name": "Apple"},
        }
        txn = {
            "investment_transaction_id": "txn_001",
            "account_id": "acc_001",
            "security_id": "sec_aapl",
            "date": date(2026, 1, 15),
            "type": "buy",
            "subtype": "buy",
            "amount": 15050.00,
            "quantity": 100,
            "price": 150.50,
            "fees": 5.00,
            "name": "Buy Apple",
            "iso_currency_code": "USD",
        }

        result = client._map_transaction(txn, securities_map)

        assert result is not None
        assert result.type == "buy"
        assert result.amount == Decimal("-15050.00")  # Flipped sign
        assert result.ticker == "AAPL"
        assert result.units == Decimal("100")
        assert result.price == Decimal("150.50")
        assert result.fee == Decimal("5.00")

    def test_maps_sell_transaction(self, mock_settings, mock_plaid_api):
        """Sell: Plaid negative amount -> our positive amount."""
        client = PlaidClient()
        securities_map = {
            "sec_aapl": {"ticker_symbol": "AAPL", "name": "Apple"},
        }
        txn = {
            "investment_transaction_id": "txn_002",
            "account_id": "acc_001",
            "security_id": "sec_aapl",
            "date": date(2026, 2, 1),
            "type": "sell",
            "subtype": "sell",
            "amount": -8000.00,
            "quantity": -50,
            "price": 160.00,
            "fees": 0,
            "name": "Sell Apple",
            "iso_currency_code": "USD",
        }

        result = client._map_transaction(txn, securities_map)

        assert result is not None
        assert result.type == "sell"
        assert result.amount == Decimal("8000.00")  # Flipped sign

    def test_maps_dividend(self, mock_settings, mock_plaid_api):
        client = PlaidClient()
        txn = {
            "investment_transaction_id": "txn_div",
            "account_id": "acc_001",
            "security_id": "sec_aapl",
            "date": date(2026, 2, 5),
            "type": "cash",
            "subtype": "dividend",
            "amount": -25.50,
            "quantity": 0,
            "price": 0,
            "name": "AAPL Dividend",
            "iso_currency_code": "USD",
        }

        result = client._map_transaction(txn, {"sec_aapl": {"ticker_symbol": "AAPL"}})

        assert result is not None
        assert result.type == "dividend"
        assert result.amount == Decimal("25.50")

    def test_skips_missing_id(self, mock_settings, mock_plaid_api):
        client = PlaidClient()
        txn = {
            "investment_transaction_id": "",
            "account_id": "acc_001",
            "date": date(2026, 1, 1),
            "type": "buy",
        }
        assert client._map_transaction(txn, {}) is None

    def test_skips_missing_date(self, mock_settings, mock_plaid_api):
        client = PlaidClient()
        txn = {
            "investment_transaction_id": "txn_001",
            "account_id": "acc_001",
            "date": None,
            "type": "buy",
        }
        assert client._map_transaction(txn, {}) is None


# ---------------------------------------------------------------------------
# Tests: Activity type mapping
# ---------------------------------------------------------------------------


class TestMapActivityType:
    def test_buy(self):
        assert PlaidClient._map_activity_type("buy", "buy") == "buy"

    def test_sell(self):
        assert PlaidClient._map_activity_type("sell", "sell") == "sell"

    def test_dividend(self):
        assert PlaidClient._map_activity_type("cash", "dividend") == "dividend"

    def test_interest(self):
        assert PlaidClient._map_activity_type("cash", "interest") == "interest"

    def test_deposit(self):
        assert PlaidClient._map_activity_type("cash", "deposit") == "deposit"

    def test_contribution(self):
        assert PlaidClient._map_activity_type("cash", "contribution") == "deposit"

    def test_withdrawal(self):
        assert PlaidClient._map_activity_type("cash", "withdrawal") == "withdrawal"

    def test_transfer(self):
        assert PlaidClient._map_activity_type("transfer", "transfer") == "transfer"

    def test_fee(self):
        assert PlaidClient._map_activity_type("fee", "management fee") == "fee"

    def test_unknown(self):
        assert PlaidClient._map_activity_type("other", "unknown") == "other"


# ---------------------------------------------------------------------------
# Tests: Cash derivation
# ---------------------------------------------------------------------------


class TestCashHandling:
    def test_cash_security_mapped_to_cash_symbol(self, mock_settings, mock_plaid_api):
        """Plaid cash securities (type=cash) are mapped to _CASH:{currency}."""
        client = PlaidClient()
        securities_map = {
            "sec_cash": {
                "security_id": "sec_cash",
                "ticker_symbol": "CUR:USD",
                "name": "US Dollar",
                "type": "cash",
                "iso_currency_code": "USD",
            },
        }
        holding_data = {
            "account_id": "acc_001",
            "security_id": "sec_cash",
            "quantity": 5000.00,
            "institution_price": 1.00,
            "institution_value": 5000.00,
            "iso_currency_code": "USD",
        }

        result = client._map_holding(holding_data, securities_map)

        assert result is not None
        assert result.symbol == "_CASH:USD"
        assert result.quantity == Decimal("5000")
        assert result.market_value == Decimal("5000")
        assert result.price == Decimal("1")
        assert result.name == "USD Cash"

    def test_cash_equivalent_security_mapped_to_cash(self, mock_settings, mock_plaid_api):
        """Securities with is_cash_equivalent=True are mapped to _CASH."""
        client = PlaidClient()
        securities_map = {
            "sec_mmf": {
                "security_id": "sec_mmf",
                "ticker_symbol": "VMFXX",
                "name": "Vanguard Federal Money Market",
                "is_cash_equivalent": True,
                "iso_currency_code": "USD",
            },
        }
        holding_data = {
            "account_id": "acc_001",
            "security_id": "sec_mmf",
            "quantity": 10000.00,
            "institution_price": 1.00,
            "institution_value": 10000.00,
            "iso_currency_code": "USD",
        }

        result = client._map_holding(holding_data, securities_map)

        assert result is not None
        assert result.symbol == "_CASH:USD"
        assert result.quantity == Decimal("10000")

    def test_cash_from_plaid_holdings_no_derivation(self, mock_settings, mock_plaid_api):
        """When Plaid provides explicit cash holdings, no cash is derived."""
        client = PlaidClient()
        mock_plaid_api.investments_holdings_get.return_value = {
            "accounts": [
                {
                    "account_id": "acc_001",
                    "name": "Brokerage",
                    "mask": "1234",
                    "balances": {"current": 50000.00, "iso_currency_code": "USD"},
                },
            ],
            "securities": [
                {
                    "security_id": "sec_1",
                    "ticker_symbol": "VTI",
                    "name": "VTI",
                    "iso_currency_code": "USD",
                },
                {
                    "security_id": "sec_cash",
                    "ticker_symbol": "CUR:USD",
                    "name": "US Dollar",
                    "type": "cash",
                    "iso_currency_code": "USD",
                },
            ],
            "holdings": [
                {
                    "account_id": "acc_001",
                    "security_id": "sec_1",
                    "quantity": 100,
                    "institution_price": 220.00,
                    "institution_value": 22000.00,
                    "iso_currency_code": "USD",
                },
                {
                    "account_id": "acc_001",
                    "security_id": "sec_cash",
                    "quantity": 28000.00,
                    "institution_price": 1.00,
                    "institution_value": 28000.00,
                    "iso_currency_code": "USD",
                },
            ],
        }

        with patch("integrations.plaid_client.ApiClient"):
            holdings, _ = client._fetch_item_holdings(
                mock_plaid_api, "access-token", "Vanguard"
            )

        # VTI + cash from Plaid, no derived cash
        assert len(holdings) == 2
        cash_holdings = [h for h in holdings if h.symbol == "_CASH:USD"]
        assert len(cash_holdings) == 1
        assert cash_holdings[0].market_value == Decimal("28000")

    def test_no_cash_when_no_cash_security(self, mock_settings, mock_plaid_api):
        """No cash holding when Plaid doesn't provide a cash security."""
        client = PlaidClient()
        mock_plaid_api.investments_holdings_get.return_value = {
            "accounts": [
                {
                    "account_id": "acc_001",
                    "name": "Brokerage",
                    "balances": {"current": 22000.00, "iso_currency_code": "USD"},
                },
            ],
            "securities": [
                {"security_id": "sec_1", "ticker_symbol": "VTI"},
            ],
            "holdings": [
                {
                    "account_id": "acc_001",
                    "security_id": "sec_1",
                    "quantity": 100,
                    "institution_price": 220.00,
                    "institution_value": 22000.00,
                    "iso_currency_code": "USD",
                },
            ],
        }

        with patch("integrations.plaid_client.ApiClient"):
            holdings, _ = client._fetch_item_holdings(
                mock_plaid_api, "access-token", "Test"
            )

        # Only VTI, no cash
        assert len(holdings) == 1
        assert holdings[0].symbol == "VTI"


# ---------------------------------------------------------------------------
# Tests: Error mapping
# ---------------------------------------------------------------------------


class TestErrorMapping:
    def test_auth_error_401(self, mock_settings):
        from plaid import ApiException
        exc = ApiException(status=401, reason="Unauthorized")
        exc.body = '{"error_code": "INVALID_ACCESS_TOKEN", "error_message": "invalid token"}'

        error = PlaidClient._map_plaid_error(exc, "Chase")

        assert error.category == ErrorCategory.AUTH
        assert error.institution_name == "Chase"
        assert not error.retriable

    def test_rate_limit_429(self, mock_settings):
        from plaid import ApiException
        exc = ApiException(status=429, reason="Rate Limit")
        exc.body = '{}'

        error = PlaidClient._map_plaid_error(exc)

        assert error.category == ErrorCategory.RATE_LIMIT
        assert error.retriable is True

    def test_server_error_500(self, mock_settings):
        from plaid import ApiException
        exc = ApiException(status=500, reason="Server Error")
        exc.body = '{}'

        error = PlaidClient._map_plaid_error(exc)

        assert error.category == ErrorCategory.CONNECTION
        assert error.retriable is True

    def test_item_login_required(self, mock_settings):
        from plaid import ApiException
        exc = ApiException(status=400, reason="Bad Request")
        exc.body = '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "login needed"}'

        error = PlaidClient._map_plaid_error(exc, "Fidelity")

        assert error.category == ErrorCategory.AUTH
        assert error.institution_name == "Fidelity"


# ---------------------------------------------------------------------------
# Tests: sync_all
# ---------------------------------------------------------------------------


class TestSyncAll:
    def test_sync_all_no_items(self, mock_settings, mock_plaid_api):
        """sync_all with no PlaidItems in DB returns empty result."""
        with patch("integrations.plaid_client.ApiClient"):
            client = PlaidClient()
        with patch.object(client, "_load_access_tokens", return_value=[]):
            result = client.sync_all()
        assert result.holdings == []
        assert result.accounts == []
        assert result.activities == []

    def test_sync_all_with_data(
        self,
        mock_settings,
        mock_plaid_api,
        sample_holdings_response,
        sample_transactions_response,
    ):
        """sync_all fetches holdings and activities for each token."""
        mock_plaid_api.investments_holdings_get.return_value = sample_holdings_response
        mock_plaid_api.investments_transactions_get.return_value = sample_transactions_response

        with patch("integrations.plaid_client.ApiClient"):
            client = PlaidClient()
        tokens = [("access-token-1", "Vanguard")]
        with patch.object(client, "_load_access_tokens", return_value=tokens):
            result = client.sync_all()

        assert isinstance(result, ProviderSyncResult)
        assert len(result.accounts) == 1
        assert result.accounts[0].name == "My Brokerage"
        assert result.accounts[0].institution == "Vanguard"

        # AAPL + synthetic fund + cash from Plaid's cash security
        assert len(result.holdings) == 3
        symbols = [h.symbol for h in result.holdings]
        assert "AAPL" in symbols
        assert "_CASH:USD" in symbols

        # 3 transactions
        assert len(result.activities) == 3

    def test_sync_all_catches_api_error(self, mock_settings, mock_plaid_api):
        """API errors on one item don't block others."""
        from plaid import ApiException
        exc = ApiException(status=400, reason="Bad Request")
        exc.body = '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "reauth needed"}'

        mock_plaid_api.investments_holdings_get.side_effect = exc
        mock_plaid_api.investments_transactions_get.side_effect = exc

        with patch("integrations.plaid_client.ApiClient"):
            client = PlaidClient()
        tokens = [("bad-token", "Chase")]
        with patch.object(client, "_load_access_tokens", return_value=tokens):
            result = client.sync_all()

        assert len(result.errors) == 1
        assert result.errors[0].category == ErrorCategory.AUTH
        assert result.errors[0].institution_name == "Chase"


# ---------------------------------------------------------------------------
# Tests: Link token and exchange
# ---------------------------------------------------------------------------


class TestLinkFlow:
    def test_create_link_token(self, mock_settings, mock_plaid_api):
        mock_plaid_api.link_token_create.return_value = {
            "link_token": "link-sandbox-abc123",
        }

        with patch("integrations.plaid_client.ApiClient"):
            client = PlaidClient()
        token = client.create_link_token()
        assert token == "link-sandbox-abc123"
        mock_plaid_api.link_token_create.assert_called_once()

    def test_exchange_public_token(self, mock_settings, mock_plaid_api):
        mock_plaid_api.item_public_token_exchange.return_value = {
            "access_token": "access-sandbox-xyz",
            "item_id": "item-sandbox-xyz",
        }

        with patch("integrations.plaid_client.ApiClient"):
            client = PlaidClient()
        result = client.exchange_public_token("public-sandbox-test")

        assert result["access_token"] == "access-sandbox-xyz"
        assert result["item_id"] == "item-sandbox-xyz"

    def test_remove_item(self, mock_settings, mock_plaid_api):
        mock_plaid_api.item_remove.return_value = {"status_code": 200}

        with patch("integrations.plaid_client.ApiClient"):
            client = PlaidClient()
        client.remove_item("access-sandbox-xyz")

        mock_plaid_api.item_remove.assert_called_once()
        call_args = mock_plaid_api.item_remove.call_args[0][0]
        assert call_args.access_token == "access-sandbox-xyz"
