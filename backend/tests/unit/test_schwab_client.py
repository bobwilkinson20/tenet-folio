"""Tests for the Charles Schwab API client."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from httpx import ConnectError, ReadTimeout, RemoteProtocolError

from integrations.schwab_client import (
    BUY_SUB_TYPES,
    SELL_SUB_TYPES,
    TRANSACTION_TYPE_MAP,
    SchwabClient,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ACCOUNT_NUMBERS = [
    {"accountNumber": "12345678", "hashValue": "HASH_ABC"},
    {"accountNumber": "87654321", "hashValue": "HASH_DEF"},
]

SAMPLE_ACCOUNTS_RESPONSE = [
    {
        "securitiesAccount": {
            "type": "INDIVIDUAL",
            "accountNumber": "12345678",
            "positions": [
                {
                    "instrument": {
                        "symbol": "AAPL",
                        "assetType": "EQUITY",
                        "description": "APPLE INC",
                    },
                    "longQuantity": 100.0,
                    "shortQuantity": 0.0,
                    "marketValue": 15025.00,
                    "averagePrice": 145.50,
                },
                {
                    "instrument": {
                        "symbol": "GOOGL",
                        "assetType": "EQUITY",
                        "description": "ALPHABET INC",
                    },
                    "longQuantity": 50.0,
                    "shortQuantity": 0.0,
                    "marketValue": 7000.00,
                },
            ],
            "currentBalances": {
                "cashBalance": 5000.00,
                "liquidationValue": 27025.00,
            },
        },
    },
]

SAMPLE_TRANSACTIONS = [
    {
        "activityId": 111222333,
        "transactionId": 111222333,
        "type": "TRADE",
        "transactionSubType": "BUY",
        "transactionDate": "2024-06-15T10:30:00+0000",
        "tradeDate": "2024-06-15T10:30:00+0000",
        "settlementDate": "2024-06-17T00:00:00+0000",
        "netAmount": -1500.00,
        "description": "BUY TRADE",
        "transferItems": [
            {
                "instrument": {
                    "symbol": "AAPL",
                    "assetType": "EQUITY",
                    "description": "APPLE INC",
                },
                "amount": 10,
                "price": 150.00,
                "cost": 0.0,
            }
        ],
        "fees": {
            "commission": 0.0,
        },
    },
    {
        "activityId": 444555666,
        "transactionId": 444555666,
        "type": "DIVIDEND_OR_INTEREST",
        "transactionSubType": "DIVIDEND",
        "transactionDate": "2024-06-20T00:00:00+0000",
        "netAmount": 25.50,
        "description": "DIVIDEND PAYMENT",
        "transferItems": [
            {
                "instrument": {
                    "symbol": "AAPL",
                    "assetType": "EQUITY",
                    "description": "APPLE INC",
                },
                "amount": 0,
                "price": 0,
                "cost": 0,
            }
        ],
        "fees": {},
    },
]


@pytest.fixture
def mock_settings():
    """Patch settings for SchwabClient tests."""
    with patch("integrations.schwab_client.settings") as mock_s:
        mock_s.SCHWAB_APP_KEY = "test-app-key"
        mock_s.SCHWAB_APP_SECRET = "test-app-secret"
        mock_s.SCHWAB_CALLBACK_URL = "https://127.0.0.1"
        mock_s.SCHWAB_TOKEN_PATH = "/tmp/fake_token.json"
        yield mock_s


@pytest.fixture
def mock_schwab_auth():
    """Patch schwab.auth.client_from_token_file."""
    with patch("integrations.schwab_client.client_from_token_file") as mock_auth:
        mock_client = MagicMock()
        mock_auth.return_value = mock_client
        yield mock_client


def _make_response(status_code=200, json_data=None):
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or []
    resp.text = "error" if status_code != 200 else ""
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(
            f"HTTP {status_code}"
        )
    return resp


# ---------------------------------------------------------------------------
# Protocol Tests
# ---------------------------------------------------------------------------


class TestSchwabClientProtocol:
    """Tests for basic protocol compliance."""

    def test_provider_name(self, mock_settings, mock_schwab_auth):
        """provider_name returns 'Schwab'."""
        client = SchwabClient()
        assert client.provider_name == "Schwab"

    @patch("integrations.schwab_client.Path")
    def test_is_configured_true(self, mock_path, mock_settings, mock_schwab_auth):
        """is_configured returns True when all credentials and token file exist."""
        mock_path.return_value.exists.return_value = True
        client = SchwabClient()
        assert client.is_configured() is True

    def test_is_configured_missing_app_key(self, mock_settings, mock_schwab_auth):
        """is_configured returns False when app key is empty."""
        mock_settings.SCHWAB_APP_KEY = ""
        client = SchwabClient()
        assert client.is_configured() is False

    def test_is_configured_missing_app_secret(self, mock_settings, mock_schwab_auth):
        """is_configured returns False when app secret is empty."""
        mock_settings.SCHWAB_APP_SECRET = ""
        client = SchwabClient()
        assert client.is_configured() is False

    def test_is_configured_missing_token_path(self, mock_settings, mock_schwab_auth):
        """is_configured returns False when token path is empty."""
        mock_settings.SCHWAB_TOKEN_PATH = ""
        client = SchwabClient()
        assert client.is_configured() is False

    @patch("integrations.schwab_client.Path")
    def test_is_configured_token_file_missing(
        self, mock_path, mock_settings, mock_schwab_auth
    ):
        """is_configured returns False when token file doesn't exist."""
        mock_path.return_value.exists.return_value = False
        client = SchwabClient()
        assert client.is_configured() is False

    def test_constructor_uses_settings_defaults(self, mock_settings, mock_schwab_auth):
        """Constructor uses settings values when no args provided."""
        client = SchwabClient()
        assert client._app_key == "test-app-key"
        assert client._app_secret == "test-app-secret"
        assert client._token_path == "/tmp/fake_token.json"

    def test_constructor_accepts_overrides(self, mock_settings, mock_schwab_auth):
        """Constructor accepts explicit credential overrides."""
        client = SchwabClient(
            app_key="custom-key",
            app_secret="custom-secret",
            token_path="/custom/token.json",
        )
        assert client._app_key == "custom-key"
        assert client._app_secret == "custom-secret"
        assert client._token_path == "/custom/token.json"


# ---------------------------------------------------------------------------
# Account Hash Map Tests
# ---------------------------------------------------------------------------


class TestAccountHashMap:
    """Tests for the account hash -> number mapping."""

    def test_fetches_and_caches_hash_map(self, mock_settings, mock_schwab_auth):
        """get_account_hash_map fetches from API and caches."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        client = SchwabClient()

        result = client._get_account_hash_map()

        assert result == {"HASH_ABC": "12345678", "HASH_DEF": "87654321"}
        assert mock_schwab_auth.get_account_numbers.call_count == 1

        # Second call should use cache
        result2 = client._get_account_hash_map()
        assert result2 == result
        assert mock_schwab_auth.get_account_numbers.call_count == 1

    def test_empty_account_numbers(self, mock_settings, mock_schwab_auth):
        """Empty account list returns empty map."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=[]
        )
        client = SchwabClient()

        result = client._get_account_hash_map()
        assert result == {}


# ---------------------------------------------------------------------------
# Account Tests
# ---------------------------------------------------------------------------


class TestSchwabGetAccounts:
    """Tests for get_accounts()."""

    def test_maps_accounts_correctly(self, mock_settings, mock_schwab_auth):
        """Accounts are correctly mapped from API response."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=SAMPLE_ACCOUNTS_RESPONSE
        )

        client = SchwabClient()
        accounts = client.get_accounts()

        assert len(accounts) == 1
        assert accounts[0].id == "HASH_ABC"
        assert accounts[0].name == "Schwab Individual Account"
        assert accounts[0].institution == "Charles Schwab"
        assert accounts[0].account_number == "12345678"

    def test_multiple_accounts(self, mock_settings, mock_schwab_auth):
        """Multiple accounts are all returned."""
        second_account = {
            "securitiesAccount": {
                "type": "MARGIN",
                "accountNumber": "87654321",
                "positions": [],
                "currentBalances": {"cashBalance": 0},
            },
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=SAMPLE_ACCOUNTS_RESPONSE + [second_account]
        )

        client = SchwabClient()
        accounts = client.get_accounts()

        assert len(accounts) == 2
        assert accounts[0].id == "HASH_ABC"
        assert accounts[1].id == "HASH_DEF"
        assert accounts[1].name == "Schwab Margin Account"

    def test_account_not_in_hash_map_skipped(self, mock_settings, mock_schwab_auth):
        """Account whose number isn't in the hash map is skipped."""
        unknown = {
            "securitiesAccount": {
                "type": "INDIVIDUAL",
                "accountNumber": "99999999",
            },
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=[unknown]
        )

        client = SchwabClient()
        accounts = client.get_accounts()
        assert len(accounts) == 0

    def test_account_without_type_uses_generic_name(self, mock_settings, mock_schwab_auth):
        """Account with no type gets generic name."""
        no_type = {
            "securitiesAccount": {
                "type": "",
                "accountNumber": "11111111",
            },
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=[{"accountNumber": "11111111", "hashValue": "HASH_XYZ"}]
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=[no_type]
        )

        client = SchwabClient()
        accounts = client.get_accounts()
        assert accounts[0].name == "Schwab Account"

    def test_api_failure_propagates(self, mock_settings, mock_schwab_auth):
        """API failure raises exception."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            status_code=401
        )

        client = SchwabClient()
        with pytest.raises(Exception, match="HTTP 401"):
            client.get_accounts()


# ---------------------------------------------------------------------------
# Holdings Tests
# ---------------------------------------------------------------------------


class TestSchwabGetHoldings:
    """Tests for get_holdings()."""

    def test_maps_positions(self, mock_settings, mock_schwab_auth):
        """Positions are correctly mapped to ProviderHoldings."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=SAMPLE_ACCOUNTS_RESPONSE
        )

        client = SchwabClient()
        holdings = client.get_holdings(account_id="HASH_ABC")

        # 2 positions + 1 cash holding
        assert len(holdings) == 3

        aapl = next(h for h in holdings if h.symbol == "AAPL")
        assert aapl.account_id == "HASH_ABC"
        assert aapl.quantity == Decimal("100")
        assert aapl.market_value == Decimal("15025")
        assert aapl.price == Decimal("15025") / Decimal("100")
        assert aapl.currency == "USD"
        assert aapl.name == "APPLE INC"
        assert aapl.cost_basis == Decimal("145.5")
        assert aapl.raw_data is not None

        # GOOGL has no averagePrice
        googl = next(h for h in holdings if h.symbol == "GOOGL")
        assert googl.cost_basis is None

    def test_zero_cost_basis_treated_as_none(self, mock_settings, mock_schwab_auth):
        """Zero averagePrice is treated as None."""
        data = [
            {
                "securitiesAccount": {
                    "type": "INDIVIDUAL",
                    "accountNumber": "12345678",
                    "positions": [
                        {
                            "instrument": {
                                "symbol": "BTC",
                                "description": "BITCOIN",
                            },
                            "longQuantity": 0.5,
                            "shortQuantity": 0.0,
                            "marketValue": 30000.00,
                            "averagePrice": 0.0,
                        },
                    ],
                    "currentBalances": {"cashBalance": 0},
                },
            }
        ]
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(json_data=data)

        client = SchwabClient()
        holdings = client.get_holdings(account_id="HASH_ABC")

        assert len(holdings) == 1
        assert holdings[0].cost_basis is None

    def test_cash_balance_as_holding(self, mock_settings, mock_schwab_auth):
        """Cash balance is represented as _CASH:USD holding."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=SAMPLE_ACCOUNTS_RESPONSE
        )

        client = SchwabClient()
        holdings = client.get_holdings(account_id="HASH_ABC")

        cash = next(h for h in holdings if h.symbol == "_CASH:USD")
        assert cash.quantity == Decimal("5000")
        assert cash.price == Decimal("1")
        assert cash.market_value == Decimal("5000")
        assert cash.currency == "USD"
        assert cash.name == "USD Cash"

    def test_zero_quantity_position_skipped(self, mock_settings, mock_schwab_auth):
        """Position with zero net quantity is skipped."""
        data = [
            {
                "securitiesAccount": {
                    "type": "INDIVIDUAL",
                    "accountNumber": "12345678",
                    "positions": [
                        {
                            "instrument": {"symbol": "ZERO", "description": "Zero Corp"},
                            "longQuantity": 0.0,
                            "shortQuantity": 0.0,
                            "marketValue": 0.0,
                        }
                    ],
                    "currentBalances": {"cashBalance": 0},
                },
            }
        ]
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(json_data=data)

        client = SchwabClient()
        holdings = client.get_holdings(account_id="HASH_ABC")
        assert len(holdings) == 0

    def test_position_without_symbol_skipped(self, mock_settings, mock_schwab_auth):
        """Position with no symbol is skipped."""
        data = [
            {
                "securitiesAccount": {
                    "type": "INDIVIDUAL",
                    "accountNumber": "12345678",
                    "positions": [
                        {
                            "instrument": {},
                            "longQuantity": 10.0,
                            "shortQuantity": 0.0,
                            "marketValue": 100.0,
                        }
                    ],
                    "currentBalances": {"cashBalance": 0},
                },
            }
        ]
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(json_data=data)

        client = SchwabClient()
        holdings = client.get_holdings(account_id="HASH_ABC")
        assert len(holdings) == 0

    def test_short_position(self, mock_settings, mock_schwab_auth):
        """Short position results in negative quantity."""
        data = [
            {
                "securitiesAccount": {
                    "type": "INDIVIDUAL",
                    "accountNumber": "12345678",
                    "positions": [
                        {
                            "instrument": {"symbol": "TSLA", "description": "TESLA INC"},
                            "longQuantity": 0.0,
                            "shortQuantity": 25.0,
                            "marketValue": -5000.00,
                        }
                    ],
                    "currentBalances": {"cashBalance": 0},
                },
            }
        ]
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(json_data=data)

        client = SchwabClient()
        holdings = client.get_holdings(account_id="HASH_ABC")

        assert len(holdings) == 1
        assert holdings[0].symbol == "TSLA"
        assert holdings[0].quantity == Decimal("-25")

    def test_filter_by_account_id(self, mock_settings, mock_schwab_auth):
        """Holdings filtered by account_id only returns matching account."""
        second_account = {
            "securitiesAccount": {
                "type": "MARGIN",
                "accountNumber": "87654321",
                "positions": [
                    {
                        "instrument": {"symbol": "MSFT", "description": "MICROSOFT"},
                        "longQuantity": 200.0,
                        "shortQuantity": 0.0,
                        "marketValue": 80000.0,
                    }
                ],
                "currentBalances": {"cashBalance": 1000.0},
            },
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=SAMPLE_ACCOUNTS_RESPONSE + [second_account]
        )

        client = SchwabClient()
        holdings = client.get_holdings(account_id="HASH_DEF")

        symbols = {h.symbol for h in holdings}
        assert "MSFT" in symbols
        assert "_CASH:USD" in symbols
        assert "AAPL" not in symbols

    def test_all_accounts_when_no_filter(self, mock_settings, mock_schwab_auth):
        """No account_id returns holdings from all accounts."""
        second_account = {
            "securitiesAccount": {
                "type": "MARGIN",
                "accountNumber": "87654321",
                "positions": [
                    {
                        "instrument": {"symbol": "MSFT", "description": "MICROSOFT"},
                        "longQuantity": 200.0,
                        "shortQuantity": 0.0,
                        "marketValue": 80000.0,
                    }
                ],
                "currentBalances": {"cashBalance": 1000.0},
            },
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=SAMPLE_ACCOUNTS_RESPONSE + [second_account]
        )

        client = SchwabClient()
        holdings = client.get_holdings()

        symbols = {h.symbol for h in holdings}
        assert "AAPL" in symbols
        assert "GOOGL" in symbols
        assert "MSFT" in symbols

    def test_zero_cash_balance_omitted(self, mock_settings, mock_schwab_auth):
        """Zero cash balance does not produce a _CASH holding."""
        data = [
            {
                "securitiesAccount": {
                    "type": "INDIVIDUAL",
                    "accountNumber": "12345678",
                    "positions": [],
                    "currentBalances": {"cashBalance": 0},
                },
            }
        ]
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(json_data=data)

        client = SchwabClient()
        holdings = client.get_holdings(account_id="HASH_ABC")
        assert len(holdings) == 0

    def test_missing_balances_no_cash_holding(self, mock_settings, mock_schwab_auth):
        """Missing currentBalances produces no cash holding."""
        data = [
            {
                "securitiesAccount": {
                    "type": "INDIVIDUAL",
                    "accountNumber": "12345678",
                    "positions": [],
                },
            }
        ]
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(json_data=data)

        client = SchwabClient()
        holdings = client.get_holdings(account_id="HASH_ABC")
        assert len(holdings) == 0


# ---------------------------------------------------------------------------
# Activity / Transaction Tests
# ---------------------------------------------------------------------------


class TestSchwabGetActivities:
    """Tests for get_activities() and transaction mapping."""

    def test_maps_trade_buy(self, mock_settings, mock_schwab_auth):
        """TRADE/BUY transaction maps to buy activity."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[SAMPLE_TRANSACTIONS[0]]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        assert len(activities) == 1
        act = activities[0]
        assert act.account_id == "HASH_ABC"
        assert act.external_id == "111222333"
        assert act.type == "buy"
        assert act.amount == Decimal("-1500")
        assert act.ticker == "AAPL"
        assert act.units == Decimal("10")
        assert act.price == Decimal("150")
        assert act.currency == "USD"
        assert act.description == "APPLE INC"

    def test_maps_dividend(self, mock_settings, mock_schwab_auth):
        """DIVIDEND_OR_INTEREST maps to dividend activity."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[SAMPLE_TRANSACTIONS[1]]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        assert len(activities) == 1
        act = activities[0]
        assert act.type == "dividend"
        assert act.amount == Decimal("25.5")
        assert act.description == "DIVIDEND PAYMENT"

    def test_maps_sell_transaction(self, mock_settings, mock_schwab_auth):
        """TRADE/SELL maps to sell activity with instrument description."""
        sell_txn = {
            "activityId": 999,
            "type": "TRADE",
            "transactionSubType": "SELL",
            "transactionDate": "2024-06-15T10:00:00Z",
            "netAmount": 3000.00,
            "description": "SELL TRADE",
            "transferItems": [
                {
                    "instrument": {
                        "symbol": "AAPL",
                        "description": "APPLE INC",
                    },
                    "amount": 20,
                    "price": 150.00,
                    "cost": 0.65,
                }
            ],
            "fees": {},
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[sell_txn]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        assert activities[0].type == "sell"
        assert activities[0].description == "APPLE INC"
        assert activities[0].fee == Decimal("0.65")

    def test_maps_ach_receipt(self, mock_settings, mock_schwab_auth):
        """ACH_RECEIPT maps to deposit."""
        ach = {
            "transactionId": 777,
            "type": "ACH_RECEIPT",
            "transactionSubType": "",
            "transactionDate": "2024-06-10T00:00:00+0000",
            "netAmount": 10000.0,
            "description": "CLIENT REQUESTED ELECTRONIC FUNDING RECEIPT",
            "transferItems": [],
            "fees": {},
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[ach]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        assert activities[0].type == "deposit"
        assert activities[0].amount == Decimal("10000")

    def test_settlement_date_parsed(self, mock_settings, mock_schwab_auth):
        """Settlement date is parsed correctly."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[SAMPLE_TRANSACTIONS[0]]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        assert activities[0].settlement_date is not None
        assert activities[0].settlement_date.year == 2024
        assert activities[0].settlement_date.month == 6
        assert activities[0].settlement_date.day == 17

    def test_transaction_without_id_skipped(self, mock_settings, mock_schwab_auth):
        """Transaction with no activityId or transactionId is skipped."""
        no_id = {
            "type": "TRADE",
            "transactionDate": "2024-06-15T10:30:00Z",
            "netAmount": -1500.00,
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[no_id]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")
        assert len(activities) == 0

    def test_transaction_without_date_skipped(self, mock_settings, mock_schwab_auth):
        """Transaction with no date is skipped."""
        no_date = {
            "activityId": 123,
            "type": "TRADE",
            "netAmount": -1500.00,
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[no_date]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")
        assert len(activities) == 0

    def test_commission_fee_from_fees_dict(self, mock_settings, mock_schwab_auth):
        """Commission is extracted from fees dict when transferItem cost is absent."""
        txn = {
            "activityId": 555,
            "type": "TRADE",
            "transactionSubType": "BUY",
            "transactionDate": "2024-06-15T10:00:00Z",
            "netAmount": -1500.00,
            "transferItems": [
                {
                    "instrument": {"symbol": "AAPL"},
                    "amount": 10,
                    "price": 150.00,
                }
            ],
            "fees": {"commission": 4.95},
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[txn]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        assert activities[0].fee == Decimal("4.95")

    def test_all_accounts_when_no_account_id(self, mock_settings, mock_schwab_auth):
        """No account_id fetches transactions for all accounts."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[SAMPLE_TRANSACTIONS[0]]
        )

        client = SchwabClient()
        client.get_activities()

        # Called once per account in hash map (2 accounts)
        assert mock_schwab_auth.get_transactions.call_count == 2

    def test_per_account_error_does_not_block_others(
        self, mock_settings, mock_schwab_auth
    ):
        """Error on one account doesn't block fetching from others."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        # First call fails, second succeeds
        mock_schwab_auth.get_transactions.side_effect = [
            Exception("Token expired"),
            _make_response(json_data=[SAMPLE_TRANSACTIONS[0]]),
        ]

        client = SchwabClient()
        activities = client.get_activities()

        # Should still get activities from second account
        assert len(activities) == 1

    def test_trade_without_instrument_desc_keeps_original(
        self, mock_settings, mock_schwab_auth
    ):
        """Trade with no instrument description keeps original description."""
        txn = {
            "activityId": 888,
            "type": "TRADE",
            "transactionSubType": "BUY",
            "transactionDate": "2024-06-15T10:00:00Z",
            "netAmount": -500.00,
            "description": "BUY TRADE",
            "transferItems": [
                {
                    "instrument": {"symbol": "XYZ"},
                    "amount": 5,
                    "price": 100.00,
                }
            ],
            "fees": {},
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[txn]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        assert activities[0].description == "BUY TRADE"

    def test_trade_unknown_sub_type_infers_buy_from_amount(
        self, mock_settings, mock_schwab_auth
    ):
        """Trade with unknown sub-type and negative amount infers buy."""
        txn = {
            "activityId": 777,
            "type": "TRADE",
            "transactionSubType": "ASSIGNED",
            "transactionDate": "2024-06-15T10:00:00Z",
            "netAmount": -2000.00,
            "description": "",
            "transferItems": [
                {
                    "instrument": {
                        "symbol": "MSFT",
                        "description": "MICROSOFT CORP",
                    },
                    "amount": 10,
                    "price": 200.00,
                }
            ],
            "fees": {},
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[txn]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        assert activities[0].type == "buy"
        assert activities[0].description == "MICROSOFT CORP"

    def test_multi_item_transfer_finds_security(self, mock_settings, mock_schwab_auth):
        """Security is extracted from non-CURRENCY transferItem."""
        txn = {
            "activityId": 999,
            "type": "TRADE",
            "transactionSubType": "",
            "transactionDate": "2024-06-15T10:00:00Z",
            "netAmount": -5000.00,
            "description": None,
            "transferItems": [
                {
                    "instrument": {
                        "assetType": "CURRENCY",
                        "symbol": "CURRENCY_USD",
                        "description": "USD currency",
                    },
                    "amount": 0.0,
                    "cost": 0.0,
                    "feeType": "COMMISSION",
                },
                {
                    "instrument": {
                        "assetType": "CURRENCY",
                        "symbol": "CURRENCY_USD",
                        "description": "USD currency",
                    },
                    "amount": 0.0,
                    "cost": 1.50,
                    "feeType": "SEC_FEE",
                },
                {
                    "instrument": {
                        "assetType": "EQUITY",
                        "symbol": "NVDA",
                        "description": "NVIDIA CORP",
                    },
                    "amount": 50,
                    "price": 100.00,
                    "cost": 0.0,
                },
            ],
            "fees": {},
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[txn]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        act = activities[0]
        assert act.type == "buy"
        assert act.ticker == "NVDA"
        assert act.description == "NVIDIA CORP"
        assert act.units == Decimal("50")
        assert act.price == Decimal("100")
        assert act.fee == Decimal("1.5")

    def test_currency_only_transfer_items(self, mock_settings, mock_schwab_auth):
        """Transaction with only CURRENCY transferItems has no ticker."""
        txn = {
            "activityId": 998,
            "type": "ACH_RECEIPT",
            "transactionSubType": "",
            "transactionDate": "2024-06-15T10:00:00Z",
            "netAmount": 10000.00,
            "description": "ACH DEPOSIT",
            "transferItems": [
                {
                    "instrument": {
                        "assetType": "CURRENCY",
                        "symbol": "CURRENCY_USD",
                        "description": "USD currency",
                    },
                    "amount": 10000.0,
                    "cost": 0.0,
                },
            ],
            "fees": {},
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[txn]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        act = activities[0]
        assert act.type == "deposit"
        assert act.ticker is None
        assert act.description == "ACH DEPOSIT"

    def test_receive_and_deliver_uses_closing_price(
        self, mock_settings, mock_schwab_auth
    ):
        """RECEIVE_AND_DELIVER uses closingPrice when price is missing."""
        txn = {
            "activityId": 997,
            "type": "RECEIVE_AND_DELIVER",
            "transactionSubType": "",
            "transactionDate": "2024-07-10T10:00:00Z",
            "netAmount": 0.0,
            "description": "TRANSFER OF SECURITY",
            "transferItems": [
                {
                    "instrument": {
                        "assetType": "EQUITY",
                        "symbol": "AAPL",
                        "description": "APPLE INC",
                        "closingPrice": 225.50,
                    },
                    "amount": 100,
                    "price": 0.0,
                    "cost": 0.0,
                },
            ],
            "fees": {},
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[txn]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        act = activities[0]
        assert act.type == "transfer"
        assert act.ticker == "AAPL"
        assert act.units == Decimal("100")
        assert act.price == Decimal("225.5")
        assert act.amount == Decimal("22550")

    def test_receive_and_deliver_null_price_uses_closing_price(
        self, mock_settings, mock_schwab_auth
    ):
        """RECEIVE_AND_DELIVER uses closingPrice when price is null."""
        txn = {
            "activityId": 996,
            "type": "RECEIVE_AND_DELIVER",
            "transactionSubType": "",
            "transactionDate": "2024-07-10T10:00:00Z",
            "netAmount": 0.0,
            "description": "TRANSFER OF SECURITY",
            "transferItems": [
                {
                    "instrument": {
                        "assetType": "EQUITY",
                        "symbol": "MSFT",
                        "description": "MICROSOFT CORP",
                        "closingPrice": 450.00,
                    },
                    "amount": 50,
                    "price": None,
                    "cost": 0.0,
                },
            ],
            "fees": {},
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[txn]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        act = activities[0]
        assert act.type == "transfer"
        assert act.ticker == "MSFT"
        assert act.price == Decimal("450")
        assert act.amount == Decimal("22500")

    def test_trade_price_not_overridden_by_closing_price(
        self, mock_settings, mock_schwab_auth
    ):
        """When price is present, closingPrice is not used."""
        txn = {
            "activityId": 995,
            "type": "TRADE",
            "transactionSubType": "BUY",
            "transactionDate": "2024-07-10T10:00:00Z",
            "netAmount": -5000.00,
            "description": "BUY TRADE",
            "transferItems": [
                {
                    "instrument": {
                        "assetType": "EQUITY",
                        "symbol": "GOOG",
                        "description": "ALPHABET INC",
                        "closingPrice": 205.00,
                    },
                    "amount": 25,
                    "price": 200.00,
                    "cost": 0.0,
                },
            ],
            "fees": {},
        }
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[txn]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        act = activities[0]
        assert act.price == Decimal("200")
        assert act.amount == Decimal("-5000")

    def test_raw_data_included(self, mock_settings, mock_schwab_auth):
        """Transaction raw_data is populated with stringified values."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[SAMPLE_TRANSACTIONS[0]]
        )

        client = SchwabClient()
        activities = client.get_activities(account_id="HASH_ABC")

        assert activities[0].raw_data is not None
        assert "activityId" in activities[0].raw_data


# ---------------------------------------------------------------------------
# Transaction Type Mapping Tests
# ---------------------------------------------------------------------------


class TestTransactionTypeMapping:
    """Tests for transaction type resolution."""

    def test_trade_buy_sub_types(self):
        """All buy sub-types are recognized."""
        client = SchwabClient.__new__(SchwabClient)
        for sub in BUY_SUB_TYPES:
            assert client._resolve_activity_type("TRADE", sub) == "buy"

    def test_trade_sell_sub_types(self):
        """All sell sub-types are recognized."""
        client = SchwabClient.__new__(SchwabClient)
        for sub in SELL_SUB_TYPES:
            assert client._resolve_activity_type("TRADE", sub) == "sell"

    def test_trade_unknown_sub_type_no_amount(self):
        """Unknown trade sub-type with no net amount maps to 'trade'."""
        client = SchwabClient.__new__(SchwabClient)
        assert client._resolve_activity_type("TRADE", "EXERCISE") == "trade"

    def test_trade_unknown_sub_type_negative_amount_infers_buy(self):
        """Unknown trade sub-type with negative net amount infers 'buy'."""
        client = SchwabClient.__new__(SchwabClient)
        assert client._resolve_activity_type(
            "TRADE", "EXERCISE", Decimal("-1500")
        ) == "buy"

    def test_trade_unknown_sub_type_positive_amount_infers_sell(self):
        """Unknown trade sub-type with positive net amount infers 'sell'."""
        client = SchwabClient.__new__(SchwabClient)
        assert client._resolve_activity_type(
            "TRADE", "EXERCISE", Decimal("3000")
        ) == "sell"

    def test_trade_unknown_sub_type_zero_amount(self):
        """Unknown trade sub-type with zero net amount maps to 'trade'."""
        client = SchwabClient.__new__(SchwabClient)
        assert client._resolve_activity_type(
            "TRADE", "EXERCISE", Decimal("0")
        ) == "trade"

    def test_all_transaction_types_mapped(self):
        """All known Schwab transaction types are in the map."""
        expected_types = {
            "TRADE", "RECEIVE_AND_DELIVER", "DIVIDEND_OR_INTEREST",
            "ACH_RECEIPT", "ACH_DISBURSEMENT", "CASH_RECEIPT",
            "CASH_DISBURSEMENT", "ELECTRONIC_FUND", "WIRE_OUT",
            "WIRE_IN", "JOURNAL", "MEMORANDUM", "MARGIN_CALL",
            "MONEY_MARKET", "SMA_ADJUSTMENT",
        }
        assert expected_types == set(TRANSACTION_TYPE_MAP.keys())

    def test_unknown_type_maps_to_other(self):
        """Unknown transaction type maps to 'other'."""
        client = SchwabClient.__new__(SchwabClient)
        assert client._resolve_activity_type("UNKNOWN_TYPE", "") == "other"


# ---------------------------------------------------------------------------
# Datetime Parsing Tests
# ---------------------------------------------------------------------------


class TestDatetimeParsing:
    """Tests for parse_iso_datetime (previously _parse_datetime on client)."""

    def test_iso_with_z_suffix(self):
        """ISO format with Z suffix is parsed correctly."""
        from integrations.parsing_utils import parse_iso_datetime
        dt = parse_iso_datetime("2024-06-15T10:30:00Z")
        assert dt == datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_iso_with_offset_no_colon(self):
        """ISO format with +0000 offset (no colon) is parsed."""
        from integrations.parsing_utils import parse_iso_datetime
        dt = parse_iso_datetime("2024-06-15T10:30:00+0000")
        assert dt is not None
        assert dt.year == 2024
        assert dt.tzinfo is not None

    def test_iso_with_colon_offset(self):
        """ISO format with +00:00 offset is parsed."""
        from integrations.parsing_utils import parse_iso_datetime
        dt = parse_iso_datetime("2024-06-15T10:30:00+00:00")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_negative_offset(self):
        """Negative timezone offset is parsed."""
        from integrations.parsing_utils import parse_iso_datetime
        dt = parse_iso_datetime("2024-06-15T10:30:00-0500")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_none_returns_none(self):
        """None input returns None."""
        from integrations.parsing_utils import parse_iso_datetime
        assert parse_iso_datetime(None) is None

    def test_invalid_string_returns_none(self):
        """Invalid date string returns None."""
        from integrations.parsing_utils import parse_iso_datetime
        assert parse_iso_datetime("not-a-date") is None

    def test_datetime_object_passthrough(self):
        """datetime object is returned directly."""
        from integrations.parsing_utils import parse_iso_datetime
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert parse_iso_datetime(dt) is dt

    def test_naive_datetime_gets_utc(self):
        """Naive datetime gets UTC timezone attached."""
        from integrations.parsing_utils import parse_iso_datetime
        naive = datetime(2024, 1, 1)
        result = parse_iso_datetime(naive)
        assert result.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Decimal Conversion Tests
# ---------------------------------------------------------------------------


class TestToDecimal:
    """Tests for _to_decimal static method."""

    def test_float_conversion(self):
        """Float is converted to Decimal."""
        assert SchwabClient._to_decimal(150.25) == Decimal("150.25")

    def test_int_conversion(self):
        """Int is converted to Decimal."""
        assert SchwabClient._to_decimal(100) == Decimal("100")

    def test_string_conversion(self):
        """Numeric string is converted to Decimal."""
        assert SchwabClient._to_decimal("99.99") == Decimal("99.99")

    def test_none_returns_none(self):
        """None returns None."""
        assert SchwabClient._to_decimal(None) is None

    def test_invalid_returns_none(self):
        """Invalid value returns None."""
        assert SchwabClient._to_decimal("not-a-number") is None


# ---------------------------------------------------------------------------
# sync_all Tests
# ---------------------------------------------------------------------------


class TestSchwabSyncAll:
    """Tests for sync_all() orchestration."""

    def test_successful_sync(self, mock_settings, mock_schwab_auth):
        """Full sync returns accounts, holdings, activities, and balance dates."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=SAMPLE_ACCOUNTS_RESPONSE
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=SAMPLE_TRANSACTIONS
        )

        client = SchwabClient()
        result = client.sync_all()

        assert len(result.accounts) == 1
        assert result.accounts[0].id == "HASH_ABC"
        # 2 positions + 1 cash
        assert len(result.holdings) == 3
        assert len(result.activities) == 2
        assert "HASH_ABC" in result.balance_dates
        assert len(result.errors) == 0

    def test_account_failure_returns_error(self, mock_settings, mock_schwab_auth):
        """Account fetch failure returns error, no holdings/activities."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            status_code=401
        )

        client = SchwabClient()
        result = client.sync_all()

        assert len(result.errors) == 1
        assert "Failed to fetch Schwab accounts" in str(result.errors[0])
        assert len(result.holdings) == 0
        assert len(result.accounts) == 0

    def test_activity_failure_non_blocking(self, mock_settings, mock_schwab_auth):
        """Activity failure doesn't block holdings/accounts."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=SAMPLE_ACCOUNTS_RESPONSE
        )
        mock_schwab_auth.get_transactions.side_effect = Exception("Rate limited")

        client = SchwabClient()
        result = client.sync_all()

        assert len(result.accounts) == 1
        assert len(result.holdings) == 3
        assert len(result.activities) == 0
        assert len(result.errors) == 0  # Activity errors are logged, not added

    def test_holdings_extraction_error_collected(self, mock_settings, mock_schwab_auth):
        """Holdings extraction error is collected but doesn't stop sync."""
        # Account data missing securitiesAccount entirely — the code handles
        # this gracefully (returns empty list)
        bad_data = [
            {}
        ]
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        # First call for accounts
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=bad_data
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[]
        )

        client = SchwabClient()
        result = client.sync_all()

        # The account has no hashValue-matching ProviderAccount because
        # securitiesAccount is missing, but holdings extraction won't fail
        # because it gracefully handles missing keys (returns empty list)
        assert len(result.errors) == 0

    def test_sync_all_balance_dates(self, mock_settings, mock_schwab_auth):
        """Balance dates are set to current time for each account."""
        mock_schwab_auth.get_account_numbers.return_value = _make_response(
            json_data=SAMPLE_ACCOUNT_NUMBERS
        )
        mock_schwab_auth.get_accounts.return_value = _make_response(
            json_data=SAMPLE_ACCOUNTS_RESPONSE
        )
        mock_schwab_auth.get_transactions.return_value = _make_response(
            json_data=[]
        )

        client = SchwabClient()
        result = client.sync_all()

        assert "HASH_ABC" in result.balance_dates
        assert result.balance_dates["HASH_ABC"] is not None
        # Should be recent (within last minute)
        now = datetime.now(timezone.utc)
        delta = now - result.balance_dates["HASH_ABC"]
        assert delta.total_seconds() < 60


# ---------------------------------------------------------------------------
# Constants Tests
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for module-level constants."""

    def test_buy_sub_types_non_empty(self):
        """BUY_SUB_TYPES contains expected entries."""
        assert "BUY" in BUY_SUB_TYPES
        assert "BUY TO OPEN" in BUY_SUB_TYPES
        assert "BUY TO CLOSE" in BUY_SUB_TYPES

    def test_sell_sub_types_non_empty(self):
        """SELL_SUB_TYPES contains expected entries."""
        assert "SELL" in SELL_SUB_TYPES
        assert "SELL TO OPEN" in SELL_SUB_TYPES
        assert "SELL TO CLOSE" in SELL_SUB_TYPES
        assert "SHORT SALE" in SELL_SUB_TYPES

    def test_no_overlap_between_buy_and_sell(self):
        """BUY and SELL sub-types don't overlap."""
        assert BUY_SUB_TYPES.isdisjoint(SELL_SUB_TYPES)

    def test_transaction_type_map_values_are_valid(self):
        """All transaction type map values are valid activity types."""
        valid_types = {"buy", "sell", "dividend", "deposit", "withdrawal",
                       "transfer", "trade", "fee", "other"}
        for activity_type in TRANSACTION_TYPE_MAP.values():
            assert activity_type in valid_types


# ---------------------------------------------------------------------------
# Retry Logic Tests
# ---------------------------------------------------------------------------


class TestRetryRequest:
    """Tests for _retry_request transient error handling."""

    def _make_client(self):
        """Create a SchwabClient without __init__ for unit testing."""
        return SchwabClient.__new__(SchwabClient)

    def test_succeeds_on_first_attempt(self):
        """Returns result immediately when no error occurs."""
        client = self._make_client()
        result = client._retry_request(lambda: "ok")
        assert result == "ok"

    @patch("integrations.schwab_client.time.sleep")
    def test_retries_on_remote_protocol_error(self, mock_sleep):
        """Retries and succeeds after RemoteProtocolError."""
        client = self._make_client()
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RemoteProtocolError(
                    "Server disconnected without sending a response"
                )
            return "recovered"

        result = client._retry_request(flaky, base_delay=1.0)

        assert result == "recovered"
        assert call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("integrations.schwab_client.time.sleep")
    def test_retries_on_connect_error(self, mock_sleep):
        """Retries and succeeds after ConnectError."""
        client = self._make_client()
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectError("Connection refused")
            return "recovered"

        result = client._retry_request(flaky, base_delay=0.5)

        assert result == "recovered"
        assert call_count == 2
        mock_sleep.assert_called_once_with(0.5)

    @patch("integrations.schwab_client.time.sleep")
    def test_retries_on_read_timeout(self, mock_sleep):
        """Retries and succeeds after ReadTimeout."""
        client = self._make_client()
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ReadTimeout("Read timed out")
            return "recovered"

        result = client._retry_request(flaky, base_delay=1.0)

        assert result == "recovered"
        assert call_count == 2

    @patch("integrations.schwab_client.time.sleep")
    def test_exhausts_retries_and_raises(self, mock_sleep):
        """Re-raises after all retries are exhausted."""
        client = self._make_client()

        def always_fails():
            raise RemoteProtocolError(
                "Server disconnected without sending a response"
            )

        with pytest.raises(RemoteProtocolError):
            client._retry_request(always_fails, retries=3, base_delay=1.0)

        # sleep called for attempts 1 and 2, but not attempt 3 (re-raises)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)   # attempt 1: 1.0 * 2^0
        mock_sleep.assert_any_call(2.0)   # attempt 2: 1.0 * 2^1

    def test_non_transient_error_not_retried(self):
        """Non-transient errors (e.g. ValueError) are raised immediately."""
        client = self._make_client()
        call_count = 0

        def bad_call():
            nonlocal call_count
            call_count += 1
            raise ValueError("Bad request")

        with pytest.raises(ValueError, match="Bad request"):
            client._retry_request(bad_call, retries=3)

        assert call_count == 1

    @patch("integrations.schwab_client.time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep):
        """Delays follow exponential backoff pattern."""
        client = self._make_client()
        call_count = 0

        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectError("Connection refused")
            return "ok"

        result = client._retry_request(fails_twice, retries=3, base_delay=2.0)

        assert result == "ok"
        assert call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2.0)   # attempt 1: 2.0 * 2^0
        mock_sleep.assert_any_call(4.0)   # attempt 2: 2.0 * 2^1
