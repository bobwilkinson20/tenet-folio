"""Unit tests for SimpleFINClient provider protocol implementation."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from integrations.exceptions import ProviderAuthError
from integrations.simplefin_client import SimpleFINClient, _generate_synthetic_symbol
from integrations.provider_protocol import ProviderAccount, ProviderHolding, ProviderSyncResult


# Test fixtures
@pytest.fixture
def mock_empty_settings():
    """Fixture that mocks settings with empty credential values."""
    with patch("integrations.simplefin_client.settings") as mock_settings:
        mock_settings.SIMPLEFIN_ACCESS_URL = ""
        yield mock_settings


@pytest.fixture
def mock_configured_settings():
    """Fixture that mocks settings with configured credentials."""
    with patch("integrations.simplefin_client.settings") as mock_settings:
        mock_settings.SIMPLEFIN_ACCESS_URL = "https://bridge.simplefin.org/simplefin/xxx"
        yield mock_settings


@pytest.fixture
def sample_simplefin_data():
    """Sample SimpleFIN data for testing (as dict, matching real API response format).

    Note: SimpleFIN API uses 'shares' field (not 'quantity') and returns numeric
    values as strings.
    """
    return {
        "accounts": [
            {
                "id": "sf_acc_001",
                "name": "Brokerage Account",
                "org": {"name": "Fidelity", "domain": "fidelity.com"},
                "balance": "50000.00",
                "currency": "USD",
                "holdings": [
                    {
                        "id": "hold_001",
                        "symbol": "AAPL",
                        "shares": "100.0",
                        "market_value": "17500.00",
                        "currency": "USD",
                        "description": "Apple Inc.",
                        "purchase_price": "150.00",
                    },
                    {
                        "id": "hold_002",
                        "symbol": "VTI",
                        "shares": "50.5",
                        "market_value": "11110.00",
                        "currency": "USD",
                        "description": "Vanguard Total Stock Market ETF",
                    },
                ],
            },
            {
                "id": "sf_acc_002",
                "name": "IRA Account",
                "org": {"name": "Vanguard"},
                "balance": "25000.00",
                "currency": "USD",
                "holdings": [
                    {
                        "id": "hold_003",
                        "symbol": "VXUS",
                        "shares": "200.0",
                        "market_value": "12000.00",
                        "currency": "USD",
                        "description": "Vanguard Total International Stock ETF",
                    },
                ],
            },
        ]
    }


@pytest.fixture
def realistic_simplefin_response():
    """Realistic SimpleFIN API response based on anonymized real data.

    This fixture represents the actual structure returned by SimpleFIN Bridge,
    including multiple account types (brokerage, crypto, 529, 401k) and various
    holding types (stocks, ETFs, crypto, target date funds).
    """
    return {
        "errors": [],
        "accounts": [
            # Brokerage account with no holdings (cash only)
            {
                "org": {
                    "domain": "www.broker.com",
                    "name": "Sample Broker",
                    "sfin-url": "https://beta-bridge.simplefin.org/simplefin",
                    "url": "https://www.broker.com/",
                    "id": "www.broker.com",
                },
                "id": "ACT-11111111-1111-1111-1111-111111111111",
                "name": "Brokerage Individual",
                "currency": "USD",
                "balance": "1500.00",
                "available-balance": "1500.00",
                "balance-date": 1769568601,
                "transactions": [],
                "holdings": [],
            },
            # Crypto account with holdings
            {
                "org": {
                    "domain": "www.broker.com",
                    "name": "Sample Broker",
                    "sfin-url": "https://beta-bridge.simplefin.org/simplefin",
                    "url": "https://www.broker.com/",
                    "id": "www.broker.com",
                },
                "id": "ACT-22222222-2222-2222-2222-222222222222",
                "name": "Crypto",
                "currency": "USD",
                "balance": "5250.00",
                "available-balance": "100.00",
                "balance-date": 1769568602,
                "transactions": [],
                "holdings": [
                    {
                        "id": "HOL-aaaa1111-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "created": 1769568602,
                        "currency": "BTC",
                        "cost_basis": "0.00",
                        "description": "Bitcoin",
                        "market_value": "5000.00",
                        "purchase_price": "0.00",
                        "shares": "0.05",
                        "symbol": "BTC",
                    },
                    {
                        "id": "HOL-aaaa2222-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "created": 1769568602,
                        "currency": "ETH",
                        "cost_basis": "0.00",
                        "description": "Ethereum",
                        "market_value": "250.00",
                        "purchase_price": "0.00",
                        "shares": "0.08",
                        "symbol": "ETH",
                    },
                ],
            },
            # 529 account with target date fund (no ticker symbol)
            {
                "org": {
                    "domain": "investor.vanguard.com",
                    "name": "Vanguard",
                    "sfin-url": "https://beta-bridge.simplefin.org/simplefin",
                    "url": "https://investor.vanguard.com/home",
                    "id": "investor.vanguard.com",
                },
                "id": "ACT-33333333-3333-3333-3333-333333333333",
                "name": "529 College Savings Account",
                "currency": "",
                "balance": "50000.00",
                "available-balance": "0.00",
                "balance-date": 1769569132,
                "transactions": [],
                "holdings": [
                    # Zero-value holdings (should be filtered out for synthetic)
                    {
                        "id": "HOL-bbbb1111-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "created": 1769569132,
                        "currency": "",
                        "cost_basis": "0.00",
                        "description": "Vanguard Conservative Income Portfolio",
                        "market_value": "0.00",
                        "purchase_price": "0.00",
                        "shares": "0.00",
                        "symbol": "",
                    },
                    # Target date fund with value (no ticker - needs synthetic symbol)
                    {
                        "id": "HOL-bbbb2222-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "created": 1769569132,
                        "currency": "",
                        "cost_basis": "0.00",
                        "description": "Vanguard Target Enrollment 2030 Portfolio",
                        "market_value": "50000.00",
                        "purchase_price": "0.00",
                        "shares": "4000.00",
                        "symbol": "",
                    },
                ],
            },
            # 401k account with ticker-based holdings
            {
                "org": {
                    "domain": "www.fidelity.com",
                    "name": "Fidelity",
                    "sfin-url": "https://beta-bridge.simplefin.org/simplefin",
                    "url": "https://www.fidelity.com/",
                    "id": "www.fidelity.com",
                },
                "id": "ACT-44444444-4444-4444-4444-444444444444",
                "name": "401(k) Plan",
                "currency": "USD",
                "balance": "150000.00",
                "available-balance": "0.00",
                "balance-date": 1769571027,
                "transactions": [],
                "holdings": [
                    {
                        "id": "HOL-cccc1111-cccc-cccc-cccc-cccccccccccc",
                        "created": 1769571027,
                        "currency": "USD",
                        "cost_basis": "70000.00",
                        "description": "Vanguard Total Stock Market Index Fund",
                        "market_value": "80000.00",
                        "purchase_price": "100.00",
                        "shares": "800.00",
                        "symbol": "VTSAX",
                    },
                    {
                        "id": "HOL-cccc2222-cccc-cccc-cccc-cccccccccccc",
                        "created": 1769571027,
                        "currency": "USD",
                        "cost_basis": "60000.00",
                        "description": "Vanguard Total Bond Market Index Fund",
                        "market_value": "70000.00",
                        "purchase_price": "10.00",
                        "shares": "7000.00",
                        "symbol": "VBTLX",
                    },
                ],
            },
        ],
    }


class TestSimpleFINClientProviderProtocol:
    """Tests for SimpleFINClient's ProviderClient protocol implementation."""

    def test_provider_name(self, mock_configured_settings):
        """SimpleFINClient returns correct provider name."""
        client = SimpleFINClient()
        assert client.provider_name == "SimpleFIN"

    def test_is_configured_true(self, mock_configured_settings):
        """is_configured returns True when access URL is present."""
        client = SimpleFINClient()
        assert client.is_configured() is True

    def test_is_configured_false(self, mock_empty_settings):
        """is_configured returns False when access URL is missing."""
        client = SimpleFINClient()
        assert client.is_configured() is False

    def test_is_configured_with_explicit_url(self, mock_empty_settings):
        """is_configured returns True when URL passed to constructor."""
        client = SimpleFINClient(access_url="https://example.com/simplefin")
        assert client.is_configured() is True

    def test_check_credentials_raises_when_not_configured(self, mock_empty_settings):
        """_check_credentials raises ProviderAuthError when not configured."""
        client = SimpleFINClient()
        with pytest.raises(ProviderAuthError) as exc_info:
            client._check_credentials()
        assert "SimpleFIN credentials not configured" in str(exc_info.value)

    def test_is_configured_false_for_base64_token(self, mock_empty_settings):
        """is_configured returns False if access URL is actually a base64 setup token."""
        # Base64 setup tokens don't start with http
        client = SimpleFINClient(access_url="aHR0cHM6Ly9iZXRhLWJyaWRnZS5zaW1wbGVmaW4ub3Jn")
        assert client.is_configured() is False

    def test_check_credentials_raises_for_base64_token(self, mock_empty_settings):
        """_check_credentials raises ProviderAuthError for base64 setup tokens."""
        client = SimpleFINClient(access_url="aHR0cHM6Ly9iZXRhLWJyaWRnZS5zaW1wbGVmaW4ub3Jn")
        with pytest.raises(ProviderAuthError) as exc_info:
            client._check_credentials()
        assert "setup token" in str(exc_info.value)
        assert "setup_simplefin.py" in str(exc_info.value)

    def test_get_accounts_maps_correctly(
        self, mock_configured_settings, sample_simplefin_data
    ):
        """get_accounts maps SimpleFIN accounts to ProviderAccount."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=sample_simplefin_data):
            accounts = client.get_accounts()

        assert len(accounts) == 2
        assert isinstance(accounts[0], ProviderAccount)

        # Check first account
        assert accounts[0].id == "sf_acc_001"
        assert accounts[0].name == "Brokerage Account"
        assert accounts[0].institution == "Fidelity"
        assert accounts[0].account_number is None

        # Check second account
        assert accounts[1].id == "sf_acc_002"
        assert accounts[1].institution == "Vanguard"

    def test_get_provider_accounts_is_alias(
        self, mock_configured_settings, sample_simplefin_data
    ):
        """get_provider_accounts is an alias for get_accounts."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=sample_simplefin_data):
            accounts1 = client.get_accounts()
            accounts2 = client.get_provider_accounts()

        assert len(accounts1) == len(accounts2)
        assert accounts1[0].id == accounts2[0].id

    def test_get_holdings_all(self, mock_configured_settings, sample_simplefin_data):
        """get_holdings returns all holdings when no account_id specified."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=sample_simplefin_data):
            holdings = client.get_holdings()

        # 3 security holdings + 2 cash holdings (sf_acc_001 and sf_acc_002 have leftover cash)
        assert len(holdings) == 5
        assert all(isinstance(h, ProviderHolding) for h in holdings)

    def test_get_holdings_filtered(
        self, mock_configured_settings, sample_simplefin_data
    ):
        """get_holdings filters by account_id when specified."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=sample_simplefin_data):
            holdings = client.get_holdings(account_id="sf_acc_001")

        # 2 security holdings + 1 cash holding (balance 50000 - holdings 28610 = 21390)
        assert len(holdings) == 3
        assert all(h.account_id == "sf_acc_001" for h in holdings)

    def test_get_holdings_maps_correctly(
        self, mock_configured_settings, sample_simplefin_data
    ):
        """get_holdings correctly maps SimpleFIN holdings to ProviderHolding."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=sample_simplefin_data):
            holdings = client.get_holdings()

        # Find the AAPL holding
        aapl = next(h for h in holdings if h.symbol == "AAPL")

        assert aapl.account_id == "sf_acc_001"
        assert aapl.symbol == "AAPL"
        assert aapl.quantity == Decimal("100.0")
        assert aapl.market_value == Decimal("17500.00")
        assert aapl.currency == "USD"
        assert aapl.name == "Apple Inc."

        # Price should be calculated from market_value / quantity
        expected_price = Decimal("17500.00") / Decimal("100.0")
        assert aapl.price == expected_price

        # Cost basis from purchase_price field
        assert aapl.cost_basis == Decimal("150.00")
        assert aapl.raw_data is not None

    def test_get_holdings_cost_basis_from_purchase_price(self, mock_configured_settings):
        """cost_basis is extracted from purchase_price field (per-unit)."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Broker"},
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "AAPL",
                            "shares": "100",
                            "market_value": "17500.00",
                            "purchase_price": "150.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert holdings[0].cost_basis == Decimal("150.00")

    def test_get_holdings_cost_basis_from_total_cost_basis(self, mock_configured_settings):
        """cost_basis falls back to cost_basis / quantity (total -> per-unit)."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Broker"},
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "VTSAX",
                            "shares": "800",
                            "market_value": "80000.00",
                            "cost_basis": "70000.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert holdings[0].cost_basis == Decimal("70000.00") / Decimal("800")

    def test_get_holdings_cost_basis_none_when_missing(self, mock_configured_settings):
        """cost_basis is None when no cost fields are present."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Broker"},
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "VTI",
                            "shares": "50",
                            "market_value": "11000.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert holdings[0].cost_basis is None

    def test_get_holdings_cost_basis_zero_purchase_price_ignored(self, mock_configured_settings):
        """purchase_price of 0 is ignored (falls through to cost_basis field)."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Broker"},
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "BTC",
                            "shares": "0.05",
                            "market_value": "5000.00",
                            "purchase_price": "0.00",
                            "cost_basis": "0.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        # Both purchase_price and cost_basis are 0, so cost_basis should be None
        assert holdings[0].cost_basis is None

    def test_get_holdings_raw_data_populated(self, mock_configured_settings):
        """raw_data contains the original holding dict."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Broker"},
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "AAPL",
                            "shares": "10",
                            "market_value": "1750.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert holdings[0].raw_data is not None
        assert holdings[0].raw_data["symbol"] == "AAPL"

    def test_get_holdings_generates_synthetic_symbol(self, mock_configured_settings):
        """Holdings without symbols get synthetic symbols generated from their ID."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Bank"},
                    "holdings": [
                        {
                            "id": "hold_target_2045",
                            "symbol": None,
                            "shares": "100.0",
                            "market_value": "5000.0",
                            "description": "Vanguard Target Retirement 2045",
                        },
                        {
                            "id": "h2",
                            "symbol": "VTI",
                            "shares": "10.0",
                            "market_value": "2200.0",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert len(holdings) == 2

        # Find the synthetic holding
        synthetic = next(h for h in holdings if h.symbol.startswith("_SF:"))
        assert synthetic.symbol == _generate_synthetic_symbol("hold_target_2045")
        assert synthetic.name == "Vanguard Target Retirement 2045"
        assert synthetic.market_value == Decimal("5000.0")

        # Regular ticker still works
        vti = next(h for h in holdings if h.symbol == "VTI")
        assert vti.market_value == Decimal("2200.0")

    def test_get_holdings_handles_zero_shares(self, mock_configured_settings):
        """Holdings with zero shares get price from purchase_price."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Bank"},
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "AAPL",
                            "shares": "0",
                            "market_value": "0",
                            "purchase_price": "150.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert len(holdings) == 1
        # With zero shares, should fall back to purchase_price
        assert holdings[0].price == Decimal("150.00")

    def test_get_holdings_empty_accounts(self, mock_configured_settings):
        """Accounts without holdings return empty list."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Bank"},
                    "holdings": None,
                },
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert holdings == []

    def test_caching_prevents_duplicate_calls(self, mock_configured_settings):
        """Data is cached to prevent unnecessary API calls."""
        data = {"accounts": []}

        with patch("integrations.simplefin_client.httpx.Client") as MockHttpxClient:
            mock_response = MagicMock()
            mock_response.json.return_value = data
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            MockHttpxClient.return_value = mock_client_instance

            client = SimpleFINClient()

            # First call should fetch
            client._fetch_data()
            # Second call should use cache
            client._fetch_data()

            # Should only have made one HTTP request
            assert mock_client_instance.get.call_count == 1

    def test_clear_cache_forces_refetch(self, mock_configured_settings):
        """clear_cache forces a fresh fetch on next request."""
        data = {"accounts": []}

        with patch("integrations.simplefin_client.httpx.Client") as MockHttpxClient:
            mock_response = MagicMock()
            mock_response.json.return_value = data
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            MockHttpxClient.return_value = mock_client_instance

            client = SimpleFINClient()

            # First call
            client._fetch_data()
            # Clear cache
            client.clear_cache()
            # Second call should fetch again
            client._fetch_data()

            # Should have made two HTTP requests
            assert mock_client_instance.get.call_count == 2


class TestSimpleFINAccountMapping:
    """Tests for SimpleFIN account edge cases."""

    def test_account_without_org(self, mock_configured_settings):
        """Account without org gets 'Unknown' institution."""
        data = {
            "accounts": [
                {"id": "acc1", "name": "Account", "org": None, "holdings": []},
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            accounts = client.get_accounts()

        assert accounts[0].institution == "Unknown"

    def test_account_without_name(self, mock_configured_settings):
        """Account without name gets default name."""
        data = {
            "accounts": [
                {"id": "acc1", "name": None, "org": {"name": "Bank"}, "holdings": []},
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            accounts = client.get_accounts()

        assert accounts[0].name == "Unnamed Account"


class TestSyntheticSymbolGeneration:
    """Tests for synthetic symbol generation."""

    def test_synthetic_symbol_is_stable(self):
        """Same holding ID always generates the same synthetic symbol."""
        holding_id = "hold_abc123"

        symbol1 = _generate_synthetic_symbol(holding_id)
        symbol2 = _generate_synthetic_symbol(holding_id)

        assert symbol1 == symbol2
        assert symbol1.startswith("_SF:")
        assert len(symbol1) == 12  # "_SF:" (4) + 8 hex chars

    def test_synthetic_symbol_format(self):
        """Synthetic symbols have correct format."""
        symbol = _generate_synthetic_symbol("test_id")

        assert symbol.startswith("_SF:")
        # Should be 8 hex characters after prefix
        hex_part = symbol[4:]
        assert len(hex_part) == 8
        # Verify it's valid hex
        int(hex_part, 16)

    def test_different_ids_produce_different_symbols(self):
        """Different holding IDs produce different symbols."""
        symbol1 = _generate_synthetic_symbol("hold_001")
        symbol2 = _generate_synthetic_symbol("hold_002")

        assert symbol1 != symbol2

    def test_get_holdings_skips_no_symbol_no_id(self, mock_configured_settings):
        """Holdings without both symbol and ID are skipped."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Bank"},
                    "holdings": [
                        # No symbol and no ID - cannot create stable symbol
                        {"symbol": None, "shares": "1000.0", "market_value": "1000.0"},
                        {
                            "id": "h2",
                            "symbol": "VTI",
                            "shares": "10.0",
                            "market_value": "2200.0",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        # Only VTI should be returned, the other is skipped
        assert len(holdings) == 1
        assert holdings[0].symbol == "VTI"

    def test_get_holdings_skips_zero_value_synthetic(self, mock_configured_settings):
        """Holdings without symbols and with zero market value are skipped."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Bank"},
                    "holdings": [
                        # No symbol, zero value - should be skipped
                        {
                            "id": "h1",
                            "symbol": None,
                            "shares": "0",
                            "market_value": "0",
                            "description": "Empty Position",
                        },
                        # No symbol, has value - should get synthetic symbol
                        {
                            "id": "h2",
                            "symbol": None,
                            "shares": "100.0",
                            "market_value": "5000.0",
                            "description": "Target Date Fund",
                        },
                        # Has symbol, zero value - should still be included
                        {
                            "id": "h3",
                            "symbol": "SOLD",
                            "shares": "0",
                            "market_value": "0",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        # Should have 2 holdings: synthetic for h2, and SOLD
        assert len(holdings) == 2
        symbols = {h.symbol for h in holdings}
        assert "SOLD" in symbols
        # h2 should have a synthetic symbol
        synthetic = next(h for h in holdings if h.symbol.startswith("_SF:"))
        assert synthetic.market_value == Decimal("5000.0")


class TestRealisticAPIResponse:
    """Tests using realistic anonymized API response data.

    These tests verify the client correctly handles real-world SimpleFIN responses,
    including the actual field names and data formats used by the API.
    """

    def test_realistic_response_accounts(
        self, mock_configured_settings, realistic_simplefin_response
    ):
        """Verify accounts are correctly parsed from realistic response."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=realistic_simplefin_response):
            accounts = client.get_accounts()

        assert len(accounts) == 4

        # Check different account types
        account_names = {a.name for a in accounts}
        assert "Brokerage Individual" in account_names
        assert "Crypto" in account_names
        assert "529 College Savings Account" in account_names
        assert "401(k) Plan" in account_names

        # Check institutions are extracted correctly
        institutions = {a.institution for a in accounts}
        assert "Sample Broker" in institutions
        assert "Vanguard" in institutions
        assert "Fidelity" in institutions

    def test_realistic_response_holdings_shares_parsed(
        self, mock_configured_settings, realistic_simplefin_response
    ):
        """Verify share counts are correctly parsed from 'shares' field."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=realistic_simplefin_response):
            holdings = client.get_holdings()

        # Find specific holdings and verify shares are parsed correctly
        btc = next(h for h in holdings if h.symbol == "BTC")
        assert btc.quantity == Decimal("0.05")
        assert btc.market_value == Decimal("5000.00")

        eth = next(h for h in holdings if h.symbol == "ETH")
        assert eth.quantity == Decimal("0.08")
        assert eth.market_value == Decimal("250.00")

        vtsax = next(h for h in holdings if h.symbol == "VTSAX")
        assert vtsax.quantity == Decimal("800.00")
        assert vtsax.market_value == Decimal("80000.00")

        vbtlx = next(h for h in holdings if h.symbol == "VBTLX")
        assert vbtlx.quantity == Decimal("7000.00")
        assert vbtlx.market_value == Decimal("70000.00")

    def test_realistic_response_price_calculated(
        self, mock_configured_settings, realistic_simplefin_response
    ):
        """Verify price is calculated from market_value / shares."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=realistic_simplefin_response):
            holdings = client.get_holdings()

        # VTSAX: 80000 / 800 = 100
        vtsax = next(h for h in holdings if h.symbol == "VTSAX")
        assert vtsax.price == Decimal("100")

        # VBTLX: 70000 / 7000 = 10
        vbtlx = next(h for h in holdings if h.symbol == "VBTLX")
        assert vbtlx.price == Decimal("10")

        # BTC: 5000 / 0.05 = 100000
        btc = next(h for h in holdings if h.symbol == "BTC")
        assert btc.price == Decimal("100000")

    def test_realistic_response_synthetic_symbols(
        self, mock_configured_settings, realistic_simplefin_response
    ):
        """Verify target date funds without tickers get synthetic symbols."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=realistic_simplefin_response):
            holdings = client.get_holdings()

        # Find the 529 target date fund (no ticker symbol in response)
        synthetic_holdings = [h for h in holdings if h.symbol.startswith("_SF:")]
        assert len(synthetic_holdings) == 1

        target_fund = synthetic_holdings[0]
        assert target_fund.name == "Vanguard Target Enrollment 2030 Portfolio"
        assert target_fund.quantity == Decimal("4000.00")
        assert target_fund.market_value == Decimal("50000.00")

    def test_realistic_response_zero_value_filtered(
        self, mock_configured_settings, realistic_simplefin_response
    ):
        """Verify zero-value holdings without symbols are filtered out."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=realistic_simplefin_response):
            holdings = client.get_holdings()

        # The "Vanguard Conservative Income Portfolio" has zero value and no symbol
        # It should be filtered out
        descriptions = {h.name for h in holdings if h.name}
        assert "Vanguard Conservative Income Portfolio" not in descriptions

    def test_realistic_response_holding_count(
        self, mock_configured_settings, realistic_simplefin_response
    ):
        """Verify correct total number of holdings after filtering."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=realistic_simplefin_response):
            holdings = client.get_holdings()

        # Expected: BTC, ETH, Target 2030 (synthetic), VTSAX, VBTLX
        # Plus 1 cash: Brokerage Individual (balance=1500, no holdings)
        # Not included: Conservative Income (zero value, no symbol)
        # Crypto, 529, 401k all have balance == holdings total so no cash
        assert len(holdings) == 6

    def test_realistic_response_filter_by_account(
        self, mock_configured_settings, realistic_simplefin_response
    ):
        """Verify filtering holdings by account works correctly."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=realistic_simplefin_response):
            # Get only 401k holdings
            holdings = client.get_holdings(
                account_id="ACT-44444444-4444-4444-4444-444444444444"
            )

        assert len(holdings) == 2
        symbols = {h.symbol for h in holdings}
        assert symbols == {"VTSAX", "VBTLX"}

    def test_realistic_response_crypto_account(
        self, mock_configured_settings, realistic_simplefin_response
    ):
        """Verify crypto holdings are parsed correctly."""
        client = SimpleFINClient()

        with patch.object(client, "_fetch_data", return_value=realistic_simplefin_response):
            holdings = client.get_holdings(
                account_id="ACT-22222222-2222-2222-2222-222222222222"
            )

        assert len(holdings) == 2

        # Verify crypto uses the symbol (BTC, ETH) not DOGE-style currency field
        symbols = {h.symbol for h in holdings}
        assert symbols == {"BTC", "ETH"}

        # Verify fractional shares work
        btc = next(h for h in holdings if h.symbol == "BTC")
        assert btc.quantity == Decimal("0.05")

    def test_shares_field_as_string(self, mock_configured_settings):
        """Verify shares field is correctly parsed when it's a string (real API format)."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Broker"},
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "AAPL",
                            "shares": "123.456",  # String format from real API
                            "market_value": "24691.20",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert holdings[0].quantity == Decimal("123.456")
        # Price = 24691.20 / 123.456 = 200
        assert holdings[0].price == Decimal("200")

    def test_sync_all_captures_errors(self, mock_configured_settings, realistic_simplefin_response):
        """sync_all() captures errors from SimpleFIN response."""
        # Add errors to the response
        realistic_simplefin_response["errors"] = [
            "Connection timeout for institution XYZ"
        ]

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=realistic_simplefin_response):
            result = client.sync_all()

        assert isinstance(result, ProviderSyncResult)
        assert len(result.errors) == 1
        assert "Connection timeout" in str(result.errors[0])
        assert len(result.holdings) > 0

    def test_sync_all_captures_balance_dates(self, mock_configured_settings, realistic_simplefin_response):
        """sync_all() captures per-account balance dates."""
        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=realistic_simplefin_response):
            result = client.sync_all()

        assert isinstance(result, ProviderSyncResult)
        # All accounts in realistic_simplefin_response have balance-date
        assert len(result.balance_dates) == 4
        for acct_id, bd in result.balance_dates.items():
            assert bd is not None
            assert isinstance(bd, datetime)

    def test_sync_all_handles_missing_errors_key(self, mock_configured_settings):
        """sync_all() handles response without errors key."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Bank"},
                    "holdings": [
                        {"id": "h1", "symbol": "AAPL", "shares": "10", "market_value": "1500"},
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            result = client.sync_all()

        assert result.errors == []
        assert len(result.holdings) == 1

    def test_sync_all_handles_missing_balance_date(self, mock_configured_settings):
        """sync_all() handles accounts without balance-date field."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Bank"},
                    "holdings": [
                        {"id": "h1", "symbol": "AAPL", "shares": "10", "market_value": "1500"},
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            result = client.sync_all()

        assert result.balance_dates["acc1"] is None

    def test_empty_string_shares(self, mock_configured_settings):
        """Verify empty string shares field is handled as zero."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Broker"},
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "AAPL",
                            "shares": "",  # Empty string
                            "market_value": "0",
                            "purchase_price": "175.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert holdings[0].quantity == Decimal("0")
        # Should fall back to purchase_price when quantity is zero
        assert holdings[0].price == Decimal("175.00")


class TestCashDerivation:
    """Tests for SimpleFIN cash derivation from account balance."""

    def test_bank_account_entire_balance_is_cash(self, mock_configured_settings):
        """Bank account with no holdings: entire balance becomes cash."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Checking",
                    "org": {"name": "Bank"},
                    "balance": "5000.00",
                    "currency": "USD",
                    "holdings": [],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert len(holdings) == 1
        assert holdings[0].symbol == "_CASH:USD"
        assert holdings[0].market_value == Decimal("5000.00")
        assert holdings[0].quantity == Decimal("5000.00")
        assert holdings[0].price == Decimal("1")
        assert holdings[0].currency == "USD"
        assert holdings[0].name == "USD Cash"

    def test_investment_account_cash_is_remainder(self, mock_configured_settings):
        """Investment account: cash = balance - sum(holdings.market_value)."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Brokerage",
                    "org": {"name": "Broker"},
                    "balance": "30000.00",
                    "currency": "USD",
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "AAPL",
                            "shares": "100",
                            "market_value": "17500.00",
                        },
                        {
                            "id": "h2",
                            "symbol": "VTI",
                            "shares": "50",
                            "market_value": "11000.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert len(holdings) == 3  # AAPL + VTI + cash
        cash = next(h for h in holdings if h.symbol == "_CASH:USD")
        assert cash.market_value == Decimal("1500.00")

    def test_no_cash_when_balance_equals_holdings(self, mock_configured_settings):
        """No cash holding created when balance equals holdings total."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Broker"},
                    "balance": "10000.00",
                    "currency": "USD",
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "VTI",
                            "shares": "50",
                            "market_value": "10000.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert len(holdings) == 1
        assert holdings[0].symbol == "VTI"

    def test_no_cash_when_balance_missing(self, mock_configured_settings):
        """No cash holding created when balance field is missing."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Bank"},
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "VTI",
                            "shares": "10",
                            "market_value": "2200.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert len(holdings) == 1
        assert holdings[0].symbol == "VTI"

    def test_negative_cash_margin_account(self, mock_configured_settings):
        """Negative cash is allowed (margin accounts)."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Margin Account",
                    "org": {"name": "Broker"},
                    "balance": "8000.00",
                    "currency": "USD",
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "AAPL",
                            "shares": "100",
                            "market_value": "15000.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert len(holdings) == 2
        cash = next(h for h in holdings if h.symbol == "_CASH:USD")
        assert cash.market_value == Decimal("-7000.00")

    def test_non_usd_currency(self, mock_configured_settings):
        """Cash uses the account's currency field."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Canadian Account",
                    "org": {"name": "Bank"},
                    "balance": "3000.00",
                    "currency": "CAD",
                    "holdings": [],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert len(holdings) == 1
        assert holdings[0].symbol == "_CASH:CAD"
        assert holdings[0].currency == "CAD"
        assert holdings[0].name == "CAD Cash"

    def test_dollar_sign_symbol_treated_as_cash(self, mock_configured_settings):
        """Holding with '$' symbol is skipped; cash derived from balance."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Altruist Brokerage",
                    "org": {"name": "Altruist"},
                    "balance": "10000.00",
                    "currency": "USD",
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "VTI",
                            "shares": "20",
                            "market_value": "4400.00",
                        },
                        {
                            "id": "h2",
                            "symbol": "$",
                            "shares": "5600",
                            "market_value": "5600.00",
                            "description": "US Dollar",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        # Should have VTI + derived cash, NOT a '$' holding
        assert len(holdings) == 2
        symbols = {h.symbol for h in holdings}
        assert "$" not in symbols
        assert "VTI" in symbols
        assert "_CASH:USD" in symbols

        # Cash should be balance - VTI market value = 10000 - 4400 = 5600
        cash = next(h for h in holdings if h.symbol == "_CASH:USD")
        assert cash.market_value == Decimal("5600.00")

    def test_currency_code_symbol_treated_as_cash(self, mock_configured_settings):
        """Holding with currency code symbol (e.g. 'USD') is skipped."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Brokerage",
                    "org": {"name": "Broker"},
                    "balance": "8000.00",
                    "currency": "USD",
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "AAPL",
                            "shares": "10",
                            "market_value": "1750.00",
                        },
                        {
                            "id": "h2",
                            "symbol": "USD",
                            "shares": "6250",
                            "market_value": "6250.00",
                            "description": "US Dollar",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        symbols = {h.symbol for h in holdings}
        assert "USD" not in symbols
        assert "_CASH:USD" in symbols

        cash = next(h for h in holdings if h.symbol == "_CASH:USD")
        assert cash.market_value == Decimal("6250.00")

    def test_cash_word_symbol_treated_as_cash(self, mock_configured_settings):
        """Holding with 'Cash' or 'CASH' symbol is skipped."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Broker"},
                    "balance": "5000.00",
                    "currency": "USD",
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "Cash",
                            "shares": "5000",
                            "market_value": "5000.00",
                            "description": "Cash & Cash Equivalents",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert len(holdings) == 1
        assert holdings[0].symbol == "_CASH:USD"

    def test_real_ticker_not_mistaken_for_cash(self, mock_configured_settings):
        """Legitimate tickers like 'CAD' are not filtered as cash symbols."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "Account",
                    "org": {"name": "Broker"},
                    "balance": "10000.00",
                    "currency": "USD",
                    "holdings": [
                        {
                            "id": "h1",
                            "symbol": "AAPL",
                            "shares": "10",
                            "market_value": "1750.00",
                        },
                    ],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        # AAPL should remain, not be filtered
        assert any(h.symbol == "AAPL" for h in holdings)

    def test_empty_string_currency_defaults_to_usd(self, mock_configured_settings):
        """Empty string currency defaults to USD."""
        data = {
            "accounts": [
                {
                    "id": "acc1",
                    "name": "529 Account",
                    "org": {"name": "Vanguard"},
                    "balance": "1000.00",
                    "currency": "",
                    "holdings": [],
                }
            ]
        }

        client = SimpleFINClient()
        with patch.object(client, "_fetch_data", return_value=data):
            holdings = client.get_holdings()

        assert len(holdings) == 1
        assert holdings[0].symbol == "_CASH:USD"
        assert holdings[0].currency == "USD"
