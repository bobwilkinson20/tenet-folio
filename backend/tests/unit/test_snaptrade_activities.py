"""Tests for SnapTrade activity parsing and fetching."""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from integrations.snaptrade_client import SnapTradeClient


@pytest.fixture
def client():
    """Create a SnapTradeClient with a mocked SDK to avoid network calls."""
    with patch("integrations.snaptrade_client.SnapTrade") as mock_sdk:
        mock_sdk.return_value = MagicMock()
        yield SnapTradeClient(
            client_id="test_client",
            consumer_key="test_key",
            user_id="test_user",
            user_secret="test_secret",
        )


class TestMapSnaptradeActivity:
    """Tests for _map_snaptrade_activity."""

    def test_maps_dict_format(self, client):
        raw = {
            "id": "txn_001",
            "account": {"id": "acc_001"},
            "type": "BUY",
            "description": "Buy AAPL",
            "trade_date": "2025-01-15",
            "settlement_date": "2025-01-17",
            "symbol": {"symbol": "AAPL"},
            "units": 10,
            "price": 150.50,
            "amount": 1505.00,
            "fee": 4.95,
            "currency": "USD",
        }

        activity = client._map_snaptrade_activity(raw)

        assert activity is not None
        assert activity.external_id == "txn_001"
        assert activity.account_id == "acc_001"
        assert activity.type == "buy"
        assert activity.description == "Buy AAPL"
        assert activity.ticker == "AAPL"
        assert activity.units == Decimal("10")
        assert activity.price == Decimal("150.50")
        assert activity.amount == Decimal("1505.00")
        assert activity.fee == Decimal("4.95")
        assert activity.currency == "USD"
        assert activity.activity_date == datetime(2025, 1, 15, tzinfo=timezone.utc)
        assert activity.settlement_date == datetime(2025, 1, 17, tzinfo=timezone.utc)

    def test_maps_object_format(self, client):
        raw = SimpleNamespace(
            id="txn_002",
            account=SimpleNamespace(id="acc_001"),
            type="SELL",
            description="Sell GOOGL",
            trade_date="2025-02-10",
            settlement_date=None,
            symbol=SimpleNamespace(symbol="GOOGL"),
            units=5,
            price=180.0,
            amount=900.0,
            fee=None,
            commission=0,
            currency="USD",
        )

        activity = client._map_snaptrade_activity(raw)

        assert activity is not None
        assert activity.external_id == "txn_002"
        assert activity.type == "sell"
        assert activity.ticker == "GOOGL"
        assert activity.settlement_date is None

    def test_returns_none_for_missing_id(self, client):
        raw = {"id": "", "trade_date": "2025-01-15"}
        activity = client._map_snaptrade_activity(raw)
        assert activity is None

    def test_returns_none_for_missing_date(self, client):
        raw = {"id": "txn_003", "trade_date": None}
        activity = client._map_snaptrade_activity(raw)
        assert activity is None

    def test_handles_no_symbol(self, client):
        raw = {
            "id": "txn_004",
            "account": "acc_001",
            "type": "DIVIDEND",
            "description": "Dividend payment",
            "trade_date": "2025-03-01",
            "symbol": None,
            "units": None,
            "price": None,
            "amount": 25.00,
            "currency": "USD",
        }
        activity = client._map_snaptrade_activity(raw)
        assert activity is not None
        assert activity.ticker is None

    def test_handles_account_as_string(self, client):
        raw = {
            "id": "txn_005",
            "account": "acc_str_id",
            "type": "transfer",
            "trade_date": "2025-01-20",
            "amount": 100.00,
        }
        activity = client._map_snaptrade_activity(raw)
        assert activity is not None
        assert activity.account_id == "acc_str_id"


class TestExtractNestedId:
    """Tests for _extract_nested_id."""

    def test_string_input(self, client):
        assert client._extract_nested_id("abc123") == "abc123"

    def test_dict_input(self, client):
        assert client._extract_nested_id({"id": "dict_id"}) == "dict_id"

    def test_object_input(self, client):
        obj = SimpleNamespace(id="obj_id")
        assert client._extract_nested_id(obj) == "obj_id"

    def test_none_input(self, client):
        assert client._extract_nested_id(None) is None


class TestParseDate:
    """Tests for parse_iso_datetime (previously _parse_date on client)."""

    def test_iso_date_string(self):
        from integrations.parsing_utils import parse_iso_datetime
        result = parse_iso_datetime("2025-01-15")
        assert result == datetime(2025, 1, 15, tzinfo=timezone.utc)

    def test_iso_datetime_string(self):
        from integrations.parsing_utils import parse_iso_datetime
        result = parse_iso_datetime("2025-01-15T10:30:00+00:00")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_datetime_object(self):
        from integrations.parsing_utils import parse_iso_datetime
        dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_iso_datetime(dt)
        assert result == dt

    def test_naive_datetime(self):
        from integrations.parsing_utils import parse_iso_datetime
        dt = datetime(2025, 6, 1, 12, 0, 0)
        result = parse_iso_datetime(dt)
        assert result.tzinfo == timezone.utc

    def test_date_object(self):
        from integrations.parsing_utils import parse_iso_datetime
        d = date(2025, 3, 15)
        result = parse_iso_datetime(d)
        assert result == datetime(2025, 3, 15, tzinfo=timezone.utc)

    def test_none_returns_none(self):
        from integrations.parsing_utils import parse_iso_datetime
        assert parse_iso_datetime(None) is None

    def test_invalid_string_returns_none(self):
        from integrations.parsing_utils import parse_iso_datetime
        assert parse_iso_datetime("not-a-date") is None


class TestExtractActivityCurrency:
    """Tests for _extract_activity_currency."""

    def test_string_currency(self, client):
        assert client._extract_activity_currency({"currency": "CAD"}) == "CAD"

    def test_dict_currency(self, client):
        assert client._extract_activity_currency(
            {"currency": {"code": "EUR"}}
        ) == "EUR"

    def test_default_usd(self, client):
        assert client._extract_activity_currency({}) == "USD"


class TestGetActivities:
    """Tests for get_activities."""

    def test_default_date_range(self, client):
        mock_response = []
        client.client.transactions_and_reporting = MagicMock()
        client.client.transactions_and_reporting.get_activities = MagicMock(
            return_value=mock_response
        )

        client.get_activities()

        call_args = client.client.transactions_and_reporting.get_activities.call_args
        assert call_args is not None
        assert "start_date" in call_args.kwargs
        assert "end_date" in call_args.kwargs

    def test_custom_date_range(self, client):
        client.client.transactions_and_reporting = MagicMock()
        client.client.transactions_and_reporting.get_activities = MagicMock(
            return_value=[]
        )

        start = date(2025, 1, 1)
        end = date(2025, 3, 31)
        client.get_activities(start_date=start, end_date=end)

        call_args = client.client.transactions_and_reporting.get_activities.call_args
        assert call_args.kwargs["start_date"] == "2025-01-01"
        assert call_args.kwargs["end_date"] == "2025-03-31"

    def test_parses_activities(self, client):
        mock_response = [
            {
                "id": "txn_001",
                "account": {"id": "acc_001"},
                "type": "BUY",
                "description": "Buy AAPL",
                "trade_date": "2025-01-15",
                "symbol": {"symbol": "AAPL"},
                "units": 10,
                "price": 150.50,
                "amount": 1505.00,
                "currency": "USD",
            }
        ]
        client.client.transactions_and_reporting = MagicMock()
        client.client.transactions_and_reporting.get_activities = MagicMock(
            return_value=mock_response
        )

        activities = client.get_activities()
        assert len(activities) == 1
        assert activities[0].ticker == "AAPL"


class TestSyncAllWithActivities:
    """Tests for sync_all including activities."""

    def test_sync_all_includes_activities(self, client):
        # Mock account list
        client.client.account_information = MagicMock()
        client.client.account_information.list_user_accounts = MagicMock(
            return_value=[
                {
                    "id": "acc_001",
                    "name": "Test Account",
                    "institution_name": "Test Broker",
                    "number": "123",
                    "sync_status": None,
                }
            ]
        )
        client.client.account_information.get_user_holdings = MagicMock(
            return_value={"positions": []}
        )

        # Mock activities
        client.client.transactions_and_reporting = MagicMock()
        client.client.transactions_and_reporting.get_activities = MagicMock(
            return_value=[
                {
                    "id": "txn_001",
                    "account": {"id": "acc_001"},
                    "type": "BUY",
                    "trade_date": "2025-01-15",
                    "amount": 100.0,
                    "currency": "USD",
                }
            ]
        )

        result = client.sync_all()
        assert len(result.activities) == 1

    def test_sync_all_activities_failure_does_not_fail_sync(self, client):
        # Mock account list
        client.client.account_information = MagicMock()
        client.client.account_information.list_user_accounts = MagicMock(
            return_value=[]
        )

        # Mock activities to fail
        client.client.transactions_and_reporting = MagicMock()
        client.client.transactions_and_reporting.get_activities = MagicMock(
            side_effect=Exception("API error")
        )

        # Should not raise
        result = client.sync_all()
        assert result.activities == []
