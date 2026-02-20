"""Unit tests for CoinbaseClient provider protocol implementation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from integrations.coinbase_client import (
    FIAT_CURRENCIES,
    V2_DESCRIPTION_MAP,
    V2_SKIP_TYPES,
    V2_TYPE_MAP,
    CoinbaseClient,
)
from integrations.provider_protocol import (
    ProviderAccount,
    ProviderSyncResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    """Fixture that mocks settings with configured Coinbase credentials."""
    with patch("integrations.coinbase_client.settings") as ms:
        ms.COINBASE_API_KEY = "organizations/org123/apiKeys/key456"
        ms.COINBASE_API_SECRET = "-----BEGIN EC PRIVATE KEY-----\nfake\n-----END EC PRIVATE KEY-----"
        ms.COINBASE_KEY_FILE = ""
        yield ms


@pytest.fixture
def mock_empty_settings():
    """Fixture that mocks settings with empty Coinbase credentials."""
    with patch("integrations.coinbase_client.settings") as ms:
        ms.COINBASE_API_KEY = ""
        ms.COINBASE_API_SECRET = ""
        ms.COINBASE_KEY_FILE = ""
        yield ms


@pytest.fixture
def mock_rest_client():
    """Fixture that provides a mocked RESTClient."""
    with patch("integrations.coinbase_client.RESTClient") as MockCls:
        client_instance = MagicMock()
        MockCls.return_value = client_instance
        yield client_instance


@pytest.fixture
def sample_portfolios():
    """Sample get_portfolios() response."""
    return {
        "portfolios": [
            {"uuid": "port-1-uuid", "name": "Default Portfolio"},
            {"uuid": "port-2-uuid", "name": "DCA Portfolio"},
        ]
    }


@pytest.fixture
def sample_fills():
    """Sample get_fills() response."""
    return {
        "fills": [
            {
                "entry_id": "fill-001",
                "trade_id": "trade-001",
                "product_id": "BTC-USD",
                "side": "BUY",
                "price": "50000.00",
                "size": "0.1",
                "commission": "5.00",
                "trade_time": "2024-06-15T10:30:00Z",
            },
            {
                "entry_id": "fill-002",
                "trade_id": "trade-002",
                "product_id": "ETH-USD",
                "side": "SELL",
                "price": "3000.00",
                "size": "2.0",
                "commission": "3.00",
                "trade_time": "2024-06-16T14:00:00Z",
            },
        ],
        "cursor": "",
    }


# ---------------------------------------------------------------------------
# TestCoinbaseClientProtocol
# ---------------------------------------------------------------------------


class TestCoinbaseClientProtocol:
    """Tests for CoinbaseClient's ProviderClient protocol implementation."""

    def test_provider_name(self, mock_settings, mock_rest_client):
        """CoinbaseClient returns correct provider name."""
        cb = CoinbaseClient()
        assert cb.provider_name == "Coinbase"

    def test_is_configured_true(self, mock_settings, mock_rest_client):
        """is_configured returns True when both key and secret are present."""
        cb = CoinbaseClient()
        assert cb.is_configured() is True

    def test_is_configured_false_no_key(self, mock_empty_settings, mock_rest_client):
        """is_configured returns False when API key is missing."""
        cb = CoinbaseClient(api_secret="secret")
        assert cb.is_configured() is False

    def test_is_configured_false_no_secret(self, mock_empty_settings, mock_rest_client):
        """is_configured returns False when API secret is missing."""
        cb = CoinbaseClient(api_key="key")
        assert cb.is_configured() is False

    def test_is_configured_false_all_empty(self, mock_empty_settings, mock_rest_client):
        """is_configured returns False when all credentials are empty."""
        cb = CoinbaseClient()
        assert cb.is_configured() is False

    def test_is_configured_with_explicit_credentials(self, mock_empty_settings, mock_rest_client):
        """is_configured returns True when credentials passed to constructor."""
        cb = CoinbaseClient(api_key="key", api_secret="secret")
        assert cb.is_configured() is True

    def test_key_file_loading_name_field(self, mock_empty_settings, mock_rest_client, tmp_path):
        """Key file with 'name' field is loaded correctly."""
        key_data = {
            "name": "organizations/org/apiKeys/key1",
            "privateKey": "-----BEGIN EC PRIVATE KEY-----\nfake\n-----END EC PRIVATE KEY-----",
        }
        key_file = tmp_path / "cdp_api_key.json"
        key_file.write_text(__import__("json").dumps(key_data))

        cb = CoinbaseClient(key_file=str(key_file))
        assert cb.is_configured() is True
        assert cb._api_key == "organizations/org/apiKeys/key1"

    def test_key_file_loading_id_field(self, mock_empty_settings, mock_rest_client, tmp_path):
        """Key file with 'id' field (instead of 'name') is loaded correctly."""
        key_data = {
            "id": "organizations/org/apiKeys/key2",
            "privateKey": "-----BEGIN EC PRIVATE KEY-----\nfake\n-----END EC PRIVATE KEY-----",
        }
        key_file = tmp_path / "cdp_api_key.json"
        key_file.write_text(__import__("json").dumps(key_data))

        cb = CoinbaseClient(key_file=str(key_file))
        assert cb.is_configured() is True
        assert cb._api_key == "organizations/org/apiKeys/key2"

    def test_key_file_missing(self, mock_empty_settings, mock_rest_client, tmp_path):
        """Missing key file does not raise, but leaves credentials empty."""
        cb = CoinbaseClient(key_file=str(tmp_path / "nonexistent.json"))
        assert cb.is_configured() is False

    def test_key_file_invalid_json(self, mock_empty_settings, mock_rest_client, tmp_path):
        """Invalid JSON key file does not raise, but leaves credentials empty."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json at all")

        cb = CoinbaseClient(key_file=str(bad_file))
        assert cb.is_configured() is False

    def test_key_file_missing_fields(self, mock_empty_settings, mock_rest_client, tmp_path):
        """Key file without name/id/privateKey leaves credentials empty."""
        key_file = tmp_path / "empty.json"
        key_file.write_text('{"unrelated": "data"}')

        cb = CoinbaseClient(key_file=str(key_file))
        assert cb.is_configured() is False


# ---------------------------------------------------------------------------
# TestCoinbaseGetAccounts
# ---------------------------------------------------------------------------


class TestCoinbaseGetAccounts:
    """Tests for portfolio → ProviderAccount mapping."""

    def test_get_accounts_maps_correctly(
        self, mock_settings, mock_rest_client, sample_portfolios
    ):
        """Portfolios are mapped to ProviderAccount objects."""
        mock_rest_client.get_portfolios.return_value = sample_portfolios
        cb = CoinbaseClient()

        accounts = cb.get_accounts()

        assert len(accounts) == 2
        assert all(isinstance(a, ProviderAccount) for a in accounts)
        assert accounts[0].id == "port-1-uuid"
        assert accounts[0].name == "Default Portfolio"
        assert accounts[0].institution == "Coinbase"
        assert accounts[1].id == "port-2-uuid"
        assert accounts[1].name == "DCA Portfolio"

    def test_get_accounts_empty(self, mock_settings, mock_rest_client):
        """Empty portfolio list returns empty account list."""
        mock_rest_client.get_portfolios.return_value = {"portfolios": []}
        cb = CoinbaseClient()

        accounts = cb.get_accounts()
        assert accounts == []

    def test_get_accounts_single(self, mock_settings, mock_rest_client):
        """Single portfolio is handled correctly."""
        mock_rest_client.get_portfolios.return_value = {
            "portfolios": [{"uuid": "solo-uuid", "name": "Solo"}]
        }
        cb = CoinbaseClient()

        accounts = cb.get_accounts()
        assert len(accounts) == 1
        assert accounts[0].id == "solo-uuid"


# ---------------------------------------------------------------------------
# TestCoinbaseGetHoldings
# ---------------------------------------------------------------------------


class TestCoinbaseGetHoldings:
    """Tests for spot position → ProviderHolding mapping via portfolio breakdown."""

    def _make_breakdown(self, positions):
        """Helper to create a get_portfolio_breakdown() response."""
        return {"breakdown": {"spot_positions": positions}}

    def test_crypto_with_fiat_valuation(self, mock_settings, mock_rest_client):
        """Crypto position derives price from fiat/crypto totals."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "BTC",
                "total_balance_crypto": "2.5",
                "total_balance_fiat": "150000.00",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 1
        h = holdings[0]
        assert h.symbol == "BTC"
        assert h.quantity == Decimal("2.5")
        assert h.price == Decimal("150000.00") / Decimal("2.5")
        assert h.market_value == Decimal("150000.00")
        assert h.currency == "USD"
        assert h.account_id == "port-1"

    def test_fiat_as_cash(self, mock_settings, mock_rest_client):
        """USD position is mapped as _CASH:USD with price=1."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "USD",
                "total_balance_crypto": "10000.00",
                "total_balance_fiat": "10000.00",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 1
        h = holdings[0]
        assert h.symbol == "_CASH:USD"
        assert h.quantity == Decimal("10000.00")
        assert h.price == Decimal("1")
        assert h.market_value == Decimal("10000.00")
        assert h.currency == "USD"

    def test_usdc_as_cash(self, mock_settings, mock_rest_client):
        """USDC is treated as cash (stablecoin)."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "USDC",
                "total_balance_crypto": "500.00",
                "total_balance_fiat": "500.00",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 1
        assert holdings[0].symbol == "_CASH:USDC"
        assert holdings[0].price == Decimal("1")

    def test_usdt_as_cash(self, mock_settings, mock_rest_client):
        """USDT is treated as cash (stablecoin)."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "USDT",
                "total_balance_crypto": "100.00",
                "total_balance_fiat": "100.00",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 1
        assert holdings[0].symbol == "_CASH:USDT"

    def test_cost_basis_from_average_entry_price(self, mock_settings, mock_rest_client):
        """cost_basis extracted from average_entry_price.value (preferred)."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "BTC",
                "total_balance_crypto": "2.5",
                "total_balance_fiat": "150000.00",
                "average_entry_price": {"value": "50000.00", "currency": "USD"},
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 1
        assert holdings[0].cost_basis == Decimal("50000.00")

    def test_cost_basis_fallback_to_total(self, mock_settings, mock_rest_client):
        """cost_basis falls back to cost_basis.value / quantity."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "ETH",
                "total_balance_crypto": "10.0",
                "total_balance_fiat": "30000.00",
                "cost_basis": {"value": "25000.00", "currency": "USD"},
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 1
        assert holdings[0].cost_basis == Decimal("25000.00") / Decimal("10.0")

    def test_cost_basis_zero_treated_as_none(self, mock_settings, mock_rest_client):
        """Zero average_entry_price is treated as None (likely invalid data)."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "BTC",
                "total_balance_crypto": "1.0",
                "total_balance_fiat": "60000.00",
                "average_entry_price": {"value": "0.00", "currency": "USD"},
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 1
        assert holdings[0].cost_basis is None

    def test_cost_basis_missing(self, mock_settings, mock_rest_client):
        """cost_basis is None when no cost fields are present."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "BTC",
                "total_balance_crypto": "1.0",
                "total_balance_fiat": "60000.00",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 1
        assert holdings[0].cost_basis is None

    def test_raw_data_on_holding(self, mock_settings, mock_rest_client):
        """raw_data is populated on holdings."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "BTC",
                "total_balance_crypto": "1.0",
                "total_balance_fiat": "60000.00",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 1
        assert holdings[0].raw_data is not None

    def test_zero_balance_filtered(self, mock_settings, mock_rest_client):
        """Zero-quantity positions are filtered out."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "DOGE",
                "total_balance_crypto": "0",
                "total_balance_fiat": "0",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")
        assert holdings == []

    def test_missing_fields_default_zero(self, mock_settings, mock_rest_client):
        """Missing total_balance fields default to 0 and position is filtered."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "XRP",
                # No total_balance_crypto or total_balance_fiat
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")
        assert holdings == []

    def test_multiple_positions(self, mock_settings, mock_rest_client):
        """Multiple spot positions are all mapped."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "BTC",
                "total_balance_crypto": "1.0",
                "total_balance_fiat": "60000.00",
            },
            {
                "asset": "ETH",
                "total_balance_crypto": "10.0",
                "total_balance_fiat": "30000.00",
            },
            {
                "asset": "USD",
                "total_balance_crypto": "5000.00",
                "total_balance_fiat": "5000.00",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 3
        symbols = {h.symbol for h in holdings}
        assert symbols == {"BTC", "ETH", "_CASH:USD"}

    def test_zero_fiat_nonzero_crypto(self, mock_settings, mock_rest_client):
        """Zero fiat with nonzero crypto yields price=0."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "SOL",
                "total_balance_crypto": "5.0",
                "total_balance_fiat": "0",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")

        assert len(holdings) == 1
        assert holdings[0].price == Decimal("0")
        assert holdings[0].market_value == Decimal("0")

    def test_empty_spot_positions(self, mock_settings, mock_rest_client):
        """Empty spot_positions list returns no holdings."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([])

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")
        assert holdings == []

    def test_missing_spot_positions(self, mock_settings, mock_rest_client):
        """Missing spot_positions key returns no holdings."""
        mock_rest_client.get_portfolio_breakdown.return_value = {"breakdown": {}}

        cb = CoinbaseClient()
        holdings = cb._get_holdings_for_portfolio("port-1")
        assert holdings == []

    def test_get_holdings_all_portfolios(
        self, mock_settings, mock_rest_client, sample_portfolios
    ):
        """get_holdings(account_id=None) fetches for all portfolios."""
        mock_rest_client.get_portfolios.return_value = sample_portfolios
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "USD",
                "total_balance_crypto": "100.00",
                "total_balance_fiat": "100.00",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb.get_holdings()

        # Should have 2 USD holdings (one per portfolio)
        assert len(holdings) == 2
        assert all(h.symbol == "_CASH:USD" for h in holdings)

    def test_get_holdings_single_portfolio(self, mock_settings, mock_rest_client):
        """get_holdings(account_id=...) fetches for only that portfolio."""
        mock_rest_client.get_portfolio_breakdown.return_value = self._make_breakdown([
            {
                "asset": "BTC",
                "total_balance_crypto": "1.0",
                "total_balance_fiat": "50000.00",
            },
        ])

        cb = CoinbaseClient()
        holdings = cb.get_holdings(account_id="specific-port")

        assert len(holdings) == 1
        assert holdings[0].account_id == "specific-port"
        # Should not call get_portfolios
        mock_rest_client.get_portfolios.assert_not_called()


# ---------------------------------------------------------------------------
# TestCoinbasePagination
# ---------------------------------------------------------------------------


class TestCoinbasePagination:
    """Tests for cursor-based pagination."""

    def test_fills_pagination(self, mock_settings, mock_rest_client):
        """Fills pagination follows cursor."""
        mock_rest_client.get_fills.side_effect = [
            {
                "fills": [{"entry_id": "f1", "product_id": "BTC-USD", "side": "BUY",
                           "price": "50000", "size": "0.1", "commission": "1",
                           "trade_time": "2024-01-01T00:00:00Z"}],
                "cursor": "page2",
            },
            {
                "fills": [{"entry_id": "f2", "product_id": "ETH-USD", "side": "SELL",
                           "price": "3000", "size": "1.0", "commission": "0.5",
                           "trade_time": "2024-01-02T00:00:00Z"}],
                "cursor": "",
            },
        ]

        cb = CoinbaseClient()
        fills = cb._get_all_fills("port-1")

        assert len(fills) == 2
        assert mock_rest_client.get_fills.call_count == 2


# ---------------------------------------------------------------------------
# TestCoinbaseGetActivities
# ---------------------------------------------------------------------------


class TestCoinbaseGetActivities:
    """Tests for fill → ProviderActivity mapping."""

    def test_buy_mapping(self, mock_settings, mock_rest_client, sample_fills):
        """BUY fill is mapped correctly with negative amount."""
        mock_rest_client.get_fills.return_value = sample_fills
        cb = CoinbaseClient()

        activities = cb.get_activities()

        buy = next(a for a in activities if a.ticker == "BTC")
        assert buy.type == "buy"
        assert buy.price == Decimal("50000.00")
        assert buy.units == Decimal("0.1")
        assert buy.amount == Decimal("-5000.00")  # Negative for buys
        assert buy.currency == "USD"
        assert buy.fee == Decimal("5.00")

    def test_sell_mapping(self, mock_settings, mock_rest_client, sample_fills):
        """SELL fill is mapped correctly with positive amount."""
        mock_rest_client.get_fills.return_value = sample_fills
        cb = CoinbaseClient()

        activities = cb.get_activities()

        sell = next(a for a in activities if a.ticker == "ETH")
        assert sell.type == "sell"
        assert sell.price == Decimal("3000.00")
        assert sell.units == Decimal("2.0")
        assert sell.amount == Decimal("6000.00")  # Positive for sells
        assert sell.currency == "USD"
        assert sell.fee == Decimal("3.00")

    def test_product_id_parsing(self, mock_settings, mock_rest_client):
        """product_id 'BTC-USD' is split into ticker='BTC', currency='USD'."""
        mock_rest_client.get_fills.return_value = {
            "fills": [
                {
                    "entry_id": "f1",
                    "product_id": "SOL-EUR",
                    "side": "BUY",
                    "price": "100",
                    "size": "5",
                    "commission": "0",
                    "trade_time": "2024-01-01T00:00:00Z",
                },
            ],
            "cursor": "",
        }
        cb = CoinbaseClient()

        activities = cb.get_activities()

        assert activities[0].ticker == "SOL"
        assert activities[0].currency == "EUR"

    def test_trade_time_parsing(self, mock_settings, mock_rest_client):
        """ISO 8601 trade_time with Z suffix is parsed to timezone-aware datetime."""
        mock_rest_client.get_fills.return_value = {
            "fills": [
                {
                    "entry_id": "f1",
                    "product_id": "BTC-USD",
                    "side": "BUY",
                    "price": "50000",
                    "size": "0.1",
                    "commission": "0",
                    "trade_time": "2024-06-15T10:30:00Z",
                },
            ],
            "cursor": "",
        }
        cb = CoinbaseClient()

        activities = cb.get_activities()

        assert activities[0].activity_date == datetime(
            2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc
        )

    def test_trade_time_iso_offset(self, mock_settings, mock_rest_client):
        """ISO 8601 trade_time with +00:00 offset is parsed correctly."""
        mock_rest_client.get_fills.return_value = {
            "fills": [
                {
                    "entry_id": "f1",
                    "product_id": "BTC-USD",
                    "side": "BUY",
                    "price": "50000",
                    "size": "0.1",
                    "commission": "0",
                    "trade_time": "2024-06-15T10:30:00+00:00",
                },
            ],
            "cursor": "",
        }
        cb = CoinbaseClient()

        activities = cb.get_activities()

        assert activities[0].activity_date.tzinfo is not None

    def test_external_id_from_entry_id(self, mock_settings, mock_rest_client):
        """entry_id is preferred as external_id."""
        mock_rest_client.get_fills.return_value = {
            "fills": [
                {
                    "entry_id": "entry-abc",
                    "trade_id": "trade-xyz",
                    "product_id": "BTC-USD",
                    "side": "BUY",
                    "price": "50000",
                    "size": "0.1",
                    "commission": "0",
                    "trade_time": "2024-01-01T00:00:00Z",
                },
            ],
            "cursor": "",
        }
        cb = CoinbaseClient()

        activities = cb.get_activities()
        assert activities[0].external_id == "entry-abc"

    def test_external_id_fallback_to_trade_id(self, mock_settings, mock_rest_client):
        """Falls back to trade_id when entry_id is missing."""
        mock_rest_client.get_fills.return_value = {
            "fills": [
                {
                    "trade_id": "trade-fallback",
                    "product_id": "BTC-USD",
                    "side": "BUY",
                    "price": "50000",
                    "size": "0.1",
                    "commission": "0",
                    "trade_time": "2024-01-01T00:00:00Z",
                },
            ],
            "cursor": "",
        }
        cb = CoinbaseClient()

        activities = cb.get_activities()
        assert activities[0].external_id == "trade-fallback"

    def test_skip_fill_without_id(self, mock_settings, mock_rest_client):
        """Fills without entry_id or trade_id are skipped."""
        mock_rest_client.get_fills.return_value = {
            "fills": [
                {
                    "product_id": "BTC-USD",
                    "side": "BUY",
                    "price": "50000",
                    "size": "0.1",
                    "trade_time": "2024-01-01T00:00:00Z",
                },
            ],
            "cursor": "",
        }
        cb = CoinbaseClient()

        activities = cb.get_activities()
        assert activities == []

    def test_skip_fill_without_trade_time(self, mock_settings, mock_rest_client):
        """Fills without trade_time are skipped."""
        mock_rest_client.get_fills.return_value = {
            "fills": [
                {
                    "entry_id": "f1",
                    "product_id": "BTC-USD",
                    "side": "BUY",
                    "price": "50000",
                    "size": "0.1",
                },
            ],
            "cursor": "",
        }
        cb = CoinbaseClient()

        activities = cb.get_activities()
        assert activities == []

    def test_raw_data_stored(self, mock_settings, mock_rest_client, sample_fills):
        """Fill dict is stored as raw_data."""
        mock_rest_client.get_fills.return_value = sample_fills
        cb = CoinbaseClient()

        activities = cb.get_activities()

        assert activities[0].raw_data is not None
        assert "entry_id" in activities[0].raw_data

    def test_description_format(self, mock_settings, mock_rest_client, sample_fills):
        """Description includes side and ticker."""
        mock_rest_client.get_fills.return_value = sample_fills
        cb = CoinbaseClient()

        activities = cb.get_activities()

        buy = next(a for a in activities if a.ticker == "BTC")
        assert "BUY" in buy.description
        assert "BTC" in buy.description

    def test_activities_with_portfolio_id(self, mock_settings, mock_rest_client, sample_fills):
        """get_activities passes portfolio_id through."""
        mock_rest_client.get_fills.return_value = sample_fills
        mock_rest_client.get_accounts.return_value = {"accounts": []}
        cb = CoinbaseClient()

        activities = cb.get_activities(account_id="port-1")

        assert all(a.account_id == "port-1" for a in activities)


# ---------------------------------------------------------------------------
# TestCoinbaseSyncAll
# ---------------------------------------------------------------------------


class TestCoinbaseSyncAll:
    """Tests for sync_all() orchestration."""

    def _mock_no_v2(self, mock_rest_client):
        """Configure mock to return no v2 currency accounts."""
        mock_rest_client.get_accounts.return_value = {"accounts": []}

    def test_sync_all_full_success(
        self, mock_settings, mock_rest_client, sample_portfolios, sample_fills
    ):
        """sync_all returns all data when everything succeeds."""
        mock_rest_client.get_portfolios.return_value = sample_portfolios
        mock_rest_client.get_portfolio_breakdown.return_value = {
            "breakdown": {
                "spot_positions": [
                    {
                        "asset": "USD",
                        "total_balance_crypto": "1000.00",
                        "total_balance_fiat": "1000.00",
                    },
                ],
            },
        }
        mock_rest_client.get_fills.return_value = sample_fills
        self._mock_no_v2(mock_rest_client)

        cb = CoinbaseClient()
        result = cb.sync_all()

        assert isinstance(result, ProviderSyncResult)
        assert len(result.accounts) == 2
        assert len(result.holdings) == 2  # 1 USD per portfolio
        # Activities fetched per-portfolio: 2 fills × 2 portfolios
        assert len(result.activities) == 4
        assert result.errors == []
        assert len(result.balance_dates) == 2

    def test_sync_all_activities_have_account_ids(
        self, mock_settings, mock_rest_client, sample_portfolios, sample_fills
    ):
        """Activities from sync_all carry the correct portfolio account_id."""
        mock_rest_client.get_portfolios.return_value = sample_portfolios
        mock_rest_client.get_portfolio_breakdown.return_value = {
            "breakdown": {"spot_positions": []},
        }
        mock_rest_client.get_fills.return_value = sample_fills
        self._mock_no_v2(mock_rest_client)

        cb = CoinbaseClient()
        result = cb.sync_all()

        # Each activity should have a real portfolio UUID, never empty
        for activity in result.activities:
            assert activity.account_id in ("port-1-uuid", "port-2-uuid")

        # First 2 activities belong to port-1, next 2 to port-2
        port1_activities = [a for a in result.activities if a.account_id == "port-1-uuid"]
        port2_activities = [a for a in result.activities if a.account_id == "port-2-uuid"]
        assert len(port1_activities) == 2
        assert len(port2_activities) == 2

    def test_sync_all_accounts_error(self, mock_settings, mock_rest_client):
        """Accounts failure returns error immediately."""
        mock_rest_client.get_portfolios.side_effect = Exception("Auth failed")

        cb = CoinbaseClient()
        result = cb.sync_all()

        assert isinstance(result, ProviderSyncResult)
        assert len(result.errors) == 1
        assert "Auth failed" in str(result.errors[0])
        assert result.holdings == []
        assert result.accounts == []
        assert result.activities == []

    def test_sync_all_holdings_error_continues(
        self, mock_settings, mock_rest_client, sample_portfolios, sample_fills
    ):
        """Holdings error for one portfolio is recorded but doesn't stop sync."""
        mock_rest_client.get_portfolios.return_value = sample_portfolios
        mock_rest_client.get_fills.return_value = sample_fills
        self._mock_no_v2(mock_rest_client)

        call_count = 0

        def breakdown_side_effect(portfolio_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Rate limited")
            return {
                "breakdown": {
                    "spot_positions": [
                        {
                            "asset": "USD",
                            "total_balance_crypto": "500.00",
                            "total_balance_fiat": "500.00",
                        },
                    ],
                },
            }

        mock_rest_client.get_portfolio_breakdown.side_effect = breakdown_side_effect

        cb = CoinbaseClient()
        result = cb.sync_all()

        assert len(result.accounts) == 2  # Both accounts returned
        assert len(result.errors) == 1  # One holdings error
        assert "Rate limited" in str(result.errors[0])
        assert len(result.holdings) == 1  # Only second portfolio succeeded
        # Activities still fetched for both portfolios (independent of holdings)
        assert len(result.activities) == 4

    def test_sync_all_activities_best_effort(
        self, mock_settings, mock_rest_client, sample_portfolios
    ):
        """Activities failure doesn't fail the sync."""
        mock_rest_client.get_portfolios.return_value = sample_portfolios
        mock_rest_client.get_portfolio_breakdown.return_value = {
            "breakdown": {
                "spot_positions": [
                    {
                        "asset": "USD",
                        "total_balance_crypto": "100.00",
                        "total_balance_fiat": "100.00",
                    },
                ],
            },
        }
        mock_rest_client.get_fills.side_effect = Exception("Fills API down")
        self._mock_no_v2(mock_rest_client)

        cb = CoinbaseClient()
        result = cb.sync_all()

        assert result.errors == []
        assert len(result.holdings) == 2
        assert len(result.accounts) == 2
        assert result.activities == []

    def test_sync_all_balance_dates(
        self, mock_settings, mock_rest_client, sample_portfolios
    ):
        """Balance dates are set to current UTC time for each portfolio."""
        mock_rest_client.get_portfolios.return_value = sample_portfolios
        mock_rest_client.get_portfolio_breakdown.return_value = {
            "breakdown": {"spot_positions": []},
        }
        mock_rest_client.get_fills.return_value = {"fills": [], "cursor": ""}
        self._mock_no_v2(mock_rest_client)

        cb = CoinbaseClient()
        result = cb.sync_all()

        assert "port-1-uuid" in result.balance_dates
        assert "port-2-uuid" in result.balance_dates
        for bd in result.balance_dates.values():
            assert bd is not None
            assert bd.tzinfo is not None


# ---------------------------------------------------------------------------
# TestFiatCurrencies
# ---------------------------------------------------------------------------


class TestFiatCurrencies:
    """Tests for the FIAT_CURRENCIES set."""

    def test_common_fiat_included(self):
        """Common fiat currencies are in the set."""
        for code in ("USD", "EUR", "GBP", "CAD", "JPY", "AUD"):
            assert code in FIAT_CURRENCIES

    def test_stablecoins_included(self):
        """USDC and USDT are treated as fiat/cash."""
        assert "USDC" in FIAT_CURRENCIES
        assert "USDT" in FIAT_CURRENCIES

    def test_crypto_not_included(self):
        """Major crypto currencies are NOT in the fiat set."""
        for code in ("BTC", "ETH", "SOL", "DOGE"):
            assert code not in FIAT_CURRENCIES


# ---------------------------------------------------------------------------
# Helpers for v2 transaction test data
# ---------------------------------------------------------------------------


def _recent_timestamp() -> str:
    """Return an ISO 8601 timestamp from 5 days ago (always within date filters)."""
    dt = datetime.now(timezone.utc) - timedelta(days=5)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_v2_txn(
    *,
    txn_id="txn-001",
    txn_type="receive",
    status="completed",
    created_at=None,
    crypto_currency="BTC",
    crypto_amount="0.5",
    native_currency="USD",
    native_amount="30000.00",
    details=None,
    network=None,
):
    """Build a minimal v2 transaction dict for testing."""
    if created_at is None:
        created_at = _recent_timestamp()
    txn = {
        "id": txn_id,
        "type": txn_type,
        "status": status,
        "created_at": created_at,
        "amount": {"amount": crypto_amount, "currency": crypto_currency},
        "native_amount": {"amount": native_amount, "currency": native_currency},
    }
    if details is not None:
        txn["details"] = details
    if network is not None:
        txn["network"] = network
    return txn


# ---------------------------------------------------------------------------
# TestCoinbaseV2Transactions — type mapping and field extraction
# ---------------------------------------------------------------------------


class TestCoinbaseV2Transactions:
    """Tests for v2 transaction → ProviderActivity mapping."""

    def test_receive_maps_to_receive(self, mock_settings, mock_rest_client):
        """V2 'receive' type maps to 'receive'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="receive")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "receive"

    def test_send_negative_maps_to_transfer(self, mock_settings, mock_rest_client):
        """V2 'send' with negative amount (outgoing) maps to 'transfer'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="send", crypto_amount="-0.5")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "transfer"

    def test_send_positive_maps_to_receive(self, mock_settings, mock_rest_client):
        """V2 'send' with positive amount (incoming) maps to 'receive'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="send", crypto_amount="180.5")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "receive"

    def test_fiat_deposit_maps_to_deposit(self, mock_settings, mock_rest_client):
        """V2 'fiat_deposit' type maps to 'deposit'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="fiat_deposit", crypto_currency="USD",
                           crypto_amount="1000.00", native_amount="1000.00")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "deposit"

    def test_fiat_withdrawal_maps_to_withdrawal(self, mock_settings, mock_rest_client):
        """V2 'fiat_withdrawal' type maps to 'withdrawal'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="fiat_withdrawal", crypto_currency="USD",
                           crypto_amount="-500.00", native_amount="-500.00")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "withdrawal"

    def test_staking_transfer_maps_to_other(self, mock_settings, mock_rest_client):
        """V2 'staking_transfer' type maps to 'other'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="staking_transfer")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "other"

    def test_unstaking_transfer_maps_to_other(self, mock_settings, mock_rest_client):
        """V2 'unstaking_transfer' type maps to 'other'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="unstaking_transfer")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "other"

    def test_earn_payout_maps_to_dividend(self, mock_settings, mock_rest_client):
        """V2 'earn_payout' type maps to 'dividend'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="earn_payout", crypto_amount="0.001",
                           native_amount="50.00")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "dividend"

    def test_staking_reward_maps_to_dividend(self, mock_settings, mock_rest_client):
        """V2 'staking_reward' type maps to 'dividend'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="staking_reward", crypto_currency="ETH",
                           crypto_amount="0.001", native_amount="3.50")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "dividend"

    def test_inflation_reward_maps_to_dividend(self, mock_settings, mock_rest_client):
        """V2 'inflation_reward' type maps to 'dividend'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="inflation_reward", crypto_currency="SOL",
                           crypto_amount="0.05", native_amount="7.50")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "dividend"

    def test_buy_maps_to_buy(self, mock_settings, mock_rest_client):
        """V2 'buy' type maps to 'buy'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="buy")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "buy"

    def test_sell_maps_to_sell(self, mock_settings, mock_rest_client):
        """V2 'sell' type maps to 'sell'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="sell", crypto_amount="-0.5",
                           native_amount="30000.00")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "sell"

    def test_trade_positive_crypto_maps_to_buy(self, mock_settings, mock_rest_client):
        """V2 'trade' with positive crypto amount maps to 'buy'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="trade", crypto_amount="1.0")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "buy"

    def test_trade_negative_crypto_maps_to_sell(self, mock_settings, mock_rest_client):
        """V2 'trade' with negative crypto amount maps to 'sell'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="trade", crypto_amount="-1.0")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "sell"

    def test_unknown_type_maps_to_other(self, mock_settings, mock_rest_client):
        """Unknown v2 type maps to 'other'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="some_new_type")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.type == "other"

    def test_skip_advanced_trade_fill(self, mock_settings, mock_rest_client):
        """V2 'advanced_trade_fill' type is skipped (duplicated by fills)."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="advanced_trade_fill")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is None

    def test_skip_pending_status(self, mock_settings, mock_rest_client):
        """Non-completed transactions are skipped."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(status="pending")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is None

    def test_skip_missing_id(self, mock_settings, mock_rest_client):
        """Transactions without an id are skipped."""
        cb = CoinbaseClient()
        txn = _make_v2_txn()
        del txn["id"]
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is None

    def test_skip_missing_created_at(self, mock_settings, mock_rest_client):
        """Transactions without created_at are skipped."""
        cb = CoinbaseClient()
        txn = _make_v2_txn()
        del txn["created_at"]
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is None

    def test_external_id_prefix(self, mock_settings, mock_rest_client):
        """External ID is prefixed with 'v2:'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_id="abc-123")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.external_id == "v2:abc-123"

    def test_ticker_from_crypto_currency(self, mock_settings, mock_rest_client):
        """Ticker is extracted from amount.currency."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(crypto_currency="ETH")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.ticker == "ETH"

    def test_units_absolute_value(self, mock_settings, mock_rest_client):
        """Units is the absolute value of crypto amount."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(crypto_amount="-2.5")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.units == Decimal("2.5")

    def test_price_derivation(self, mock_settings, mock_rest_client):
        """Price = |native_amount| / |crypto_amount|."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(crypto_amount="0.5", native_amount="30000.00")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.price == Decimal("60000")

    def test_price_none_when_zero_crypto(self, mock_settings, mock_rest_client):
        """Price is None when crypto amount is zero."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(crypto_amount="0", native_amount="0")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.price is None

    def test_fee_extraction(self, mock_settings, mock_rest_client):
        """Fee is extracted from network.transaction_fee.amount."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(network={
            "transaction_fee": {"amount": "0.0001", "currency": "BTC"}
        })
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.fee == Decimal("0.0001")

    def test_fee_none_when_no_network(self, mock_settings, mock_rest_client):
        """Fee is None when network field is absent."""
        cb = CoinbaseClient()
        txn = _make_v2_txn()
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.fee is None

    def test_description_from_details_title(self, mock_settings, mock_rest_client):
        """Description comes from details.title when present."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(details={"title": "Received Bitcoin"})
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.description == "Received Bitcoin"

    def test_description_fallback_receive(self, mock_settings, mock_rest_client):
        """Description falls back to human-readable template for 'receive'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="receive", crypto_currency="BTC",
                           crypto_amount="0.5")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.description == "Received 0.5 BTC"

    def test_description_fallback_send_outgoing(self, mock_settings, mock_rest_client):
        """Outgoing 'send' (negative amount) description says 'Sent'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="send", crypto_currency="ETH",
                           crypto_amount="-8.12")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.description == "Sent 8.12 ETH"

    def test_description_fallback_send_incoming(self, mock_settings, mock_rest_client):
        """Incoming 'send' (positive amount) description says 'Received'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="send", crypto_currency="SOL",
                           crypto_amount="180.5")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.description == "Received 180.5 SOL"

    def test_description_fallback_staking_transfer(self, mock_settings, mock_rest_client):
        """Description falls back to human-readable template for 'staking_transfer'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="staking_transfer", crypto_currency="ETH",
                           crypto_amount="8.12")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.description == "Staked 8.12 ETH"

    def test_description_fallback_unstaking_transfer(self, mock_settings, mock_rest_client):
        """Description falls back to human-readable template for 'unstaking_transfer'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="unstaking_transfer", crypto_currency="ETH",
                           crypto_amount="8.12")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.description == "Unstaked 8.12 ETH"

    def test_description_fallback_staking_reward(self, mock_settings, mock_rest_client):
        """Description falls back to human-readable template for 'staking_reward'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="staking_reward", crypto_currency="ETH",
                           crypto_amount="0.001")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.description == "Staking reward: 0.001 ETH"

    def test_description_fallback_inflation_reward(self, mock_settings, mock_rest_client):
        """Description falls back to human-readable template for 'inflation_reward'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="inflation_reward", crypto_currency="SOL",
                           crypto_amount="0.05")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.description == "Staking reward: 0.05 SOL"

    def test_description_fallback_earn_payout(self, mock_settings, mock_rest_client):
        """Description falls back to human-readable template for 'earn_payout'."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="earn_payout", crypto_currency="USDC",
                           crypto_amount="0.50")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.description == "Earn payout: 0.50 USDC"

    def test_description_fallback_unknown_type(self, mock_settings, mock_rest_client):
        """Description falls back to 'TYPE TICKER on Coinbase' for unknown types."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(txn_type="some_new_type", crypto_currency="BTC")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.description == "OTHER BTC on Coinbase"

    def test_raw_data_stored(self, mock_settings, mock_rest_client):
        """Raw transaction data is stored."""
        cb = CoinbaseClient()
        txn = _make_v2_txn()
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.raw_data is not None

    def test_portfolio_id_as_account_id(self, mock_settings, mock_rest_client):
        """account_id is set to the portfolio UUID, not the currency account."""
        cb = CoinbaseClient()
        txn = _make_v2_txn()
        result = cb._map_v2_transaction(txn, "my-portfolio-uuid")
        assert result is not None
        assert result.account_id == "my-portfolio-uuid"

    def test_amount_is_absolute_native(self, mock_settings, mock_rest_client):
        """amount is the absolute value of native_amount."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(native_amount="-500.00")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.amount == Decimal("500.00")

    def test_currency_from_native_amount(self, mock_settings, mock_rest_client):
        """Currency comes from native_amount.currency."""
        cb = CoinbaseClient()
        txn = _make_v2_txn(native_currency="EUR")
        result = cb._map_v2_transaction(txn, "port-1")
        assert result is not None
        assert result.currency == "EUR"


# ---------------------------------------------------------------------------
# TestCoinbaseV2Pagination
# ---------------------------------------------------------------------------


class TestCoinbaseV2Pagination:
    """Tests for v2 account and transaction pagination."""

    def test_currency_accounts_pagination(self, mock_settings, mock_rest_client):
        """Currency accounts pagination follows next_starting_after."""
        mock_rest_client.get_accounts.side_effect = [
            {
                "accounts": [{"uuid": "ca-1", "name": "BTC Wallet"}],
                "pagination": {"next_starting_after": "ca-1"},
            },
            {
                "accounts": [{"uuid": "ca-2", "name": "ETH Wallet"}],
                "pagination": {"next_starting_after": None},
            },
        ]

        cb = CoinbaseClient()
        accounts = cb._get_currency_accounts("port-1")

        assert len(accounts) == 2
        assert mock_rest_client.get_accounts.call_count == 2

    def test_v2_transactions_pagination(self, mock_settings, mock_rest_client):
        """V2 transactions pagination follows starting_after."""
        mock_rest_client.get.side_effect = [
            {
                "data": [_make_v2_txn(txn_id="txn-1")],
                "pagination": {"next_starting_after": "txn-1"},
            },
            {
                "data": [_make_v2_txn(txn_id="txn-2")],
                "pagination": {"next_starting_after": None},
            },
        ]

        cb = CoinbaseClient()
        txns = cb._get_v2_transactions("ca-uuid")

        assert len(txns) == 2
        assert mock_rest_client.get.call_count == 2
        # Verify params kwarg was used (SDK signing requirement)
        for call in mock_rest_client.get.call_args_list:
            assert "params" in call.kwargs

    def test_currency_account_error_doesnt_block_others(
        self, mock_settings, mock_rest_client
    ):
        """API error on one currency account doesn't block others."""
        mock_rest_client.get_accounts.return_value = {
            "accounts": [
                {"uuid": "ca-1", "name": "BTC Wallet"},
                {"uuid": "ca-2", "name": "ETH Wallet"},
            ],
            "pagination": {},
        }

        call_count = 0

        def get_side_effect(url, params=None):
            nonlocal call_count
            call_count += 1
            if "ca-1" in url:
                raise Exception("API Error")
            return {
                "data": [_make_v2_txn(txn_id="txn-from-ca2", crypto_currency="ETH")],
                "pagination": {},
            }

        mock_rest_client.get.side_effect = get_side_effect

        cb = CoinbaseClient()
        activities = cb._get_all_v2_transactions("port-1")

        # Only ca-2's transaction should come through
        assert len(activities) == 1
        assert activities[0].ticker == "ETH"


# ---------------------------------------------------------------------------
# TestCoinbaseV2Integration — combining fills + v2
# ---------------------------------------------------------------------------


class TestCoinbaseV2Integration:
    """Tests for get_activities combining fills and v2 transactions."""

    def _setup_fills_and_v2(self, mock_rest_client, sample_fills):
        """Configure mock for both fills and v2 transactions."""
        mock_rest_client.get_fills.return_value = sample_fills
        mock_rest_client.get_accounts.return_value = {
            "accounts": [{"uuid": "ca-btc", "name": "BTC Wallet"}],
            "pagination": {},
        }
        mock_rest_client.get.return_value = {
            "data": [
                _make_v2_txn(txn_id="v2-recv-1", txn_type="receive",
                             crypto_currency="BTC", crypto_amount="0.25",
                             native_amount="15000.00"),
            ],
            "pagination": {},
        }

    def test_get_activities_combines_fills_and_v2(
        self, mock_settings, mock_rest_client, sample_fills
    ):
        """get_activities returns both fills and v2 transactions."""
        self._setup_fills_and_v2(mock_rest_client, sample_fills)

        cb = CoinbaseClient()
        activities = cb.get_activities(account_id="port-1")

        # 2 fills + 1 v2 transaction
        assert len(activities) == 3
        fill_ids = {a.external_id for a in activities if not a.external_id.startswith("v2:")}
        v2_ids = {a.external_id for a in activities if a.external_id.startswith("v2:")}
        assert len(fill_ids) == 2
        assert len(v2_ids) == 1

    def test_get_activities_no_account_id_returns_only_fills(
        self, mock_settings, mock_rest_client, sample_fills
    ):
        """get_activities(account_id=None) returns only fills, no v2."""
        mock_rest_client.get_fills.return_value = sample_fills

        cb = CoinbaseClient()
        activities = cb.get_activities(account_id=None)

        # Only fills, no v2 calls
        assert len(activities) == 2
        assert all(not a.external_id.startswith("v2:") for a in activities)
        mock_rest_client.get_accounts.assert_not_called()

    def test_v2_error_still_returns_fills(
        self, mock_settings, mock_rest_client, sample_fills
    ):
        """V2 error doesn't prevent fills from returning."""
        mock_rest_client.get_fills.return_value = sample_fills
        mock_rest_client.get_accounts.side_effect = Exception("V2 API down")

        cb = CoinbaseClient()
        activities = cb.get_activities(account_id="port-1")

        # Only fills returned
        assert len(activities) == 2
        assert all(not a.external_id.startswith("v2:") for a in activities)

    def test_sync_all_includes_v2_transactions(
        self, mock_settings, mock_rest_client, sample_portfolios, sample_fills
    ):
        """sync_all includes v2 transactions alongside fills."""
        mock_rest_client.get_portfolios.return_value = sample_portfolios
        mock_rest_client.get_portfolio_breakdown.return_value = {
            "breakdown": {"spot_positions": []},
        }
        mock_rest_client.get_fills.return_value = sample_fills
        mock_rest_client.get_accounts.return_value = {
            "accounts": [{"uuid": "ca-btc"}],
            "pagination": {},
        }
        mock_rest_client.get.return_value = {
            "data": [
                _make_v2_txn(txn_id="v2-dep", txn_type="receive"),
            ],
            "pagination": {},
        }

        cb = CoinbaseClient()
        result = cb.sync_all()

        # 2 portfolios × (2 fills + 1 v2) = 6 activities
        assert len(result.activities) == 6
        v2_count = sum(1 for a in result.activities if a.external_id.startswith("v2:"))
        fill_count = sum(1 for a in result.activities if not a.external_id.startswith("v2:"))
        assert v2_count == 2  # 1 per portfolio
        assert fill_count == 4  # 2 per portfolio

    def test_advanced_trade_fill_not_duplicated(
        self, mock_settings, mock_rest_client, sample_fills
    ):
        """advanced_trade_fill in v2 is skipped, avoiding duplication with fills."""
        mock_rest_client.get_fills.return_value = sample_fills
        mock_rest_client.get_accounts.return_value = {
            "accounts": [{"uuid": "ca-btc"}],
            "pagination": {},
        }
        mock_rest_client.get.return_value = {
            "data": [
                _make_v2_txn(txn_id="atf-1", txn_type="advanced_trade_fill"),
                _make_v2_txn(txn_id="v2-recv", txn_type="receive"),
            ],
            "pagination": {},
        }

        cb = CoinbaseClient()
        activities = cb.get_activities(account_id="port-1")

        # 2 fills + 1 v2 receive (advanced_trade_fill skipped)
        assert len(activities) == 3
        external_ids = {a.external_id for a in activities}
        assert "v2:atf-1" not in external_ids
        assert "v2:v2-recv" in external_ids


# ---------------------------------------------------------------------------
# TestV2Constants
# ---------------------------------------------------------------------------


class TestV2Constants:
    """Tests for V2_TYPE_MAP and V2_SKIP_TYPES constants."""

    def test_v2_type_map_keys(self):
        """V2_TYPE_MAP contains expected transaction types."""
        expected_keys = {
            "send", "receive", "fiat_deposit", "fiat_withdrawal",
            "staking_transfer", "unstaking_transfer", "earn_payout",
            "staking_reward", "inflation_reward",
            "transfer", "buy", "sell",
        }
        assert set(V2_TYPE_MAP.keys()) == expected_keys

    def test_v2_skip_types(self):
        """V2_SKIP_TYPES contains advanced_trade_fill."""
        assert "advanced_trade_fill" in V2_SKIP_TYPES

    def test_v2_description_map_keys(self):
        """V2_DESCRIPTION_MAP has templates for key transaction types."""
        expected_keys = {
            "send", "receive", "staking_transfer", "unstaking_transfer",
            "staking_reward", "inflation_reward", "earn_payout",
        }
        assert set(V2_DESCRIPTION_MAP.keys()) == expected_keys


# ---------------------------------------------------------------------------
# TestCoinbaseDateFiltering
# ---------------------------------------------------------------------------


class TestCoinbaseDateFiltering:
    """Tests for date range filtering on activities."""

    def test_fills_passes_start_sequence_timestamp(self, mock_settings, mock_rest_client):
        """_get_all_fills passes start_sequence_timestamp to the API."""
        mock_rest_client.get_fills.return_value = {"fills": [], "cursor": ""}

        cb = CoinbaseClient()
        cb._get_all_fills("port-1", days=90)

        call_kwargs = mock_rest_client.get_fills.call_args.kwargs
        assert "start_sequence_timestamp" in call_kwargs
        # Timestamp should be roughly 90 days ago in ISO format
        ts = call_kwargs["start_sequence_timestamp"]
        assert ts.endswith("Z")

    def test_fills_custom_days(self, mock_settings, mock_rest_client):
        """_get_all_fills accepts a custom days parameter."""
        mock_rest_client.get_fills.return_value = {"fills": [], "cursor": ""}

        cb = CoinbaseClient()
        cb._get_all_fills("port-1", days=30)

        call_kwargs = mock_rest_client.get_fills.call_args.kwargs
        ts = call_kwargs["start_sequence_timestamp"]
        # Parse the timestamp and verify it's roughly 30 days ago
        parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        expected = datetime.now(timezone.utc) - timedelta(days=30)
        assert abs((parsed - expected).total_seconds()) < 60

    def test_v2_transactions_filtered_by_date(self, mock_settings, mock_rest_client):
        """_get_all_v2_transactions filters out old transactions."""
        # Create one recent and one old transaction
        recent_date = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        old_date = (datetime.now(timezone.utc) - timedelta(days=200)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        mock_rest_client.get_accounts.return_value = {
            "accounts": [{"uuid": "ca-1"}],
            "pagination": {},
        }
        mock_rest_client.get.return_value = {
            "data": [
                _make_v2_txn(txn_id="recent", created_at=recent_date),
                _make_v2_txn(txn_id="old", created_at=old_date),
            ],
            "pagination": {},
        }

        cb = CoinbaseClient()
        activities = cb._get_all_v2_transactions("port-1", days=90)

        assert len(activities) == 1
        assert activities[0].external_id == "v2:recent"

    def test_v2_transactions_custom_days(self, mock_settings, mock_rest_client):
        """_get_all_v2_transactions respects custom days parameter."""
        # Transaction is 20 days old — within 30 days but outside 10 days
        txn_date = (datetime.now(timezone.utc) - timedelta(days=20)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        mock_rest_client.get_accounts.return_value = {
            "accounts": [{"uuid": "ca-1"}],
            "pagination": {},
        }
        mock_rest_client.get.return_value = {
            "data": [_make_v2_txn(txn_id="mid-age", created_at=txn_date)],
            "pagination": {},
        }

        cb = CoinbaseClient()

        # Within 30-day window
        activities_30 = cb._get_all_v2_transactions("port-1", days=30)
        assert len(activities_30) == 1

        # Outside 10-day window
        activities_10 = cb._get_all_v2_transactions("port-1", days=10)
        assert len(activities_10) == 0

    def test_get_activities_threads_days_param(self, mock_settings, mock_rest_client):
        """get_activities passes days parameter to fills and v2."""
        mock_rest_client.get_fills.return_value = {"fills": [], "cursor": ""}
        mock_rest_client.get_accounts.return_value = {
            "accounts": [],
            "pagination": {},
        }

        cb = CoinbaseClient()
        cb.get_activities(account_id="port-1", days=30)

        # Verify fills got the start_sequence_timestamp (indicating days was threaded)
        call_kwargs = mock_rest_client.get_fills.call_args.kwargs
        ts = call_kwargs["start_sequence_timestamp"]
        parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        expected = datetime.now(timezone.utc) - timedelta(days=30)
        assert abs((parsed - expected).total_seconds()) < 60
