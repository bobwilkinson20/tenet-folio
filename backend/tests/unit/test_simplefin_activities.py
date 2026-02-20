"""Tests for SimpleFIN activity parsing and fetching."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from integrations.simplefin_client import SimpleFINClient


@pytest.fixture
def client():
    """Create a SimpleFINClient with a mock access URL."""
    c = SimpleFINClient(access_url="https://test.simplefin.example/api")
    return c


@pytest.fixture
def sample_data():
    """Sample SimpleFIN API response with transactions."""
    return {
        "accounts": [
            {
                "id": "sf_acc_001",
                "name": "Checking",
                "org": {"name": "Chase"},
                "transactions": [
                    {
                        "id": "txn_001",
                        "posted": 1705363200,  # 2024-01-16 00:00:00 UTC
                        "amount": "-50.00",
                        "payee": "Amazon",
                        "description": "Purchase",
                        "memo": "Order #123",
                    },
                    {
                        "id": "txn_002",
                        "posted": 1705449600,  # 2024-01-17 00:00:00 UTC
                        "amount": "2500.00",
                        "payee": "Employer Inc",
                        "description": "Direct Deposit",
                    },
                    {
                        "id": "txn_003",
                        "posted": 1705536000,  # 2024-01-18 00:00:00 UTC
                        "amount": "15.75",
                        "payee": "Vanguard",
                        "description": "Dividend Distribution",
                    },
                ],
                "holdings": [],
            },
            {
                "id": "sf_acc_002",
                "name": "Investment",
                "org": {"name": "Schwab"},
                "transactions": [
                    {
                        "id": "txn_004",
                        "posted": 1705622400,  # 2024-01-19 00:00:00 UTC
                        "amount": "-1500.00",
                        "payee": "Schwab",
                        "description": "Buy SPY",
                    },
                ],
                "holdings": [],
            },
        ],
        "errors": [],
    }


class TestMapSimplefinTransaction:
    """Tests for _map_simplefin_transaction."""

    def test_maps_basic_transaction(self, client):
        txn = {
            "id": "txn_001",
            "posted": 1705363200,
            "amount": "-50.00",
            "payee": "Amazon",
            "description": "Purchase",
            "memo": "Order #123",
        }

        activity = client._map_simplefin_transaction(txn, "sf_acc_001")

        assert activity is not None
        assert activity.external_id == "txn_001"
        assert activity.account_id == "sf_acc_001"
        assert activity.amount == Decimal("-50.00")
        assert activity.description == "Amazon - Purchase - Order #123"
        assert activity.activity_date.year == 2024

    def test_returns_none_for_missing_id(self, client):
        txn = {"posted": 1705363200, "amount": "100"}
        activity = client._map_simplefin_transaction(txn, "acc_001")
        assert activity is None

    def test_returns_none_for_missing_date(self, client):
        txn = {"id": "txn_no_date", "amount": "100"}
        activity = client._map_simplefin_transaction(txn, "acc_001")
        assert activity is None

    def test_builds_description_from_parts(self, client):
        # Only payee
        txn = {"id": "t1", "posted": 1705363200, "payee": "Store"}
        act = client._map_simplefin_transaction(txn, "acc")
        assert act.description == "Store"

        # Payee + description
        txn = {"id": "t2", "posted": 1705363200, "payee": "Store", "description": "Groceries"}
        act = client._map_simplefin_transaction(txn, "acc")
        assert act.description == "Store - Groceries"

        # All three
        txn = {"id": "t3", "posted": 1705363200, "payee": "Store", "description": "Groceries", "memo": "Card ending 1234"}
        act = client._map_simplefin_transaction(txn, "acc")
        assert act.description == "Store - Groceries - Card ending 1234"

        # None
        txn = {"id": "t4", "posted": 1705363200}
        act = client._map_simplefin_transaction(txn, "acc")
        assert act.description is None

    def test_stores_raw_data(self, client):
        txn = {"id": "txn_raw", "posted": 1705363200, "amount": "10"}
        act = client._map_simplefin_transaction(txn, "acc")
        assert act.raw_data == txn

    def test_uses_transacted_at_fallback(self, client):
        txn = {"id": "txn_fb", "transacted_at": 1705363200, "amount": "10"}
        act = client._map_simplefin_transaction(txn, "acc")
        assert act is not None
        assert act.activity_date.year == 2024

    def test_extracts_currency(self, client):
        txn = {"id": "txn_cur", "posted": 1705363200, "amount": "10", "currency": "CAD"}
        act = client._map_simplefin_transaction(txn, "acc")
        assert act.currency == "CAD"


class TestInferActivityType:
    """Tests for _infer_activity_type."""

    def test_dividend_keywords(self, client):
        assert client._infer_activity_type(
            {"description": "Dividend Distribution"}, Decimal("15.75")
        ) == "dividend"

    def test_interest_keyword(self, client):
        assert client._infer_activity_type(
            {"description": "Interest Payment"}, Decimal("5.00")
        ) == "interest"

    def test_buy_keyword(self, client):
        assert client._infer_activity_type(
            {"description": "Buy SPY"}, Decimal("-1500")
        ) == "buy"

    def test_sell_keyword(self, client):
        assert client._infer_activity_type(
            {"payee": "Broker", "description": "Sold AAPL"}, Decimal("3000")
        ) == "sell"

    def test_transfer_keyword(self, client):
        assert client._infer_activity_type(
            {"description": "Transfer from savings"}, Decimal("500")
        ) == "transfer"

    def test_fee_keyword(self, client):
        assert client._infer_activity_type(
            {"description": "Account fee"}, Decimal("-25")
        ) == "fee"

    def test_deposit_keyword(self, client):
        assert client._infer_activity_type(
            {"description": "Direct Deposit"}, Decimal("2500")
        ) == "deposit"

    def test_withdrawal_keyword(self, client):
        assert client._infer_activity_type(
            {"description": "ATM Withdrawal"}, Decimal("-200")
        ) == "withdrawal"

    def test_positive_amount_fallback(self, client):
        assert client._infer_activity_type(
            {"description": "Something"}, Decimal("100")
        ) == "deposit"

    def test_negative_amount_fallback(self, client):
        assert client._infer_activity_type(
            {"description": "Something"}, Decimal("-100")
        ) == "withdrawal"

    def test_zero_amount_fallback(self, client):
        assert client._infer_activity_type(
            {"description": "Something"}, Decimal("0")
        ) == "other"

    def test_none_amount_fallback(self, client):
        assert client._infer_activity_type(
            {"description": "Something"}, None
        ) == "other"


class TestParseUnixTimestamp:
    """Tests for parse_unix_timestamp (previously _parse_unix_timestamp on client)."""

    def test_valid_timestamp(self):
        from integrations.parsing_utils import parse_unix_timestamp
        result = parse_unix_timestamp(1705363200)
        assert result is not None
        assert result.year == 2024
        assert result.tzinfo == timezone.utc

    def test_string_timestamp(self):
        from integrations.parsing_utils import parse_unix_timestamp
        result = parse_unix_timestamp("1705363200")
        assert result is not None

    def test_none_returns_none(self):
        from integrations.parsing_utils import parse_unix_timestamp
        assert parse_unix_timestamp(None) is None

    def test_invalid_returns_none(self):
        from integrations.parsing_utils import parse_unix_timestamp
        assert parse_unix_timestamp("not-a-number") is None


class TestGetActivities:
    """Tests for get_activities."""

    def test_fetches_all_activities(self, client, sample_data):
        client._cache = sample_data
        client._cache_time = datetime.now()

        activities = client.get_activities()
        assert len(activities) == 4

    def test_filters_by_account(self, client, sample_data):
        client._cache = sample_data
        client._cache_time = datetime.now()

        activities = client.get_activities(account_id="sf_acc_001")
        assert len(activities) == 3
        assert all(a.account_id == "sf_acc_001" for a in activities)

    def test_empty_when_no_transactions(self, client):
        client._cache = {"accounts": [{"id": "acc", "name": "Empty", "org": {"name": "Bank"}}]}
        client._cache_time = datetime.now()

        activities = client.get_activities()
        assert len(activities) == 0


class TestSyncAllWithActivities:
    """Tests for sync_all including activities."""

    def test_sync_all_includes_activities(self, client, sample_data):
        client._cache = sample_data
        client._cache_time = datetime.now()

        result = client.sync_all()
        assert len(result.activities) == 4

    def test_sync_all_activities_failure_does_not_fail_sync(self, client):
        """If get_activities raises, sync_all still returns holdings/accounts."""
        data = {
            "accounts": [
                {
                    "id": "acc_001",
                    "name": "Account",
                    "org": {"name": "Bank"},
                    "holdings": [],
                }
            ],
            "errors": [],
        }
        client._cache = data
        client._cache_time = datetime.now()

        # Monkey-patch get_activities to raise
        original = client.get_activities
        def failing_get_activities(**kwargs):
            raise Exception("Activity fetch failed")
        client.get_activities = failing_get_activities

        result = client.sync_all()
        assert result.activities == []
        assert len(result.accounts) == 1

        # Restore
        client.get_activities = original
