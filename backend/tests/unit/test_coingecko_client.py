"""Unit tests for CoinGeckoClient (mocked httpx)."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from integrations.coingecko_client import CoinGeckoClient, _KNOWN_COIN_IDS


@pytest.fixture
def client():
    return CoinGeckoClient()


@pytest.fixture
def client_with_key():
    return CoinGeckoClient(api_key="test-api-key")


def _make_market_chart_response(prices: list[list[float]]) -> dict:
    """Build a CoinGecko /market_chart/range response."""
    return {"prices": prices}


def _ts_ms(year: int, month: int, day: int, hour: int = 0) -> float:
    """Convert a date to unix timestamp in milliseconds."""
    return datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp() * 1000


class TestProviderName:
    def test_provider_name(self, client):
        assert client.provider_name == "coingecko"


class TestKnownCoinIds:
    def test_common_coins_in_mapping(self):
        """Verify the most common coins are in the hardcoded mapping."""
        assert _KNOWN_COIN_IDS["BTC"] == "bitcoin"
        assert _KNOWN_COIN_IDS["ETH"] == "ethereum"
        assert _KNOWN_COIN_IDS["SOL"] == "solana"
        assert _KNOWN_COIN_IDS["SUI"] == "sui"
        assert _KNOWN_COIN_IDS["DOGE"] == "dogecoin"
        assert _KNOWN_COIN_IDS["ADA"] == "cardano"
        assert _KNOWN_COIN_IDS["XRP"] == "ripple"


class TestSymbolResolution:
    def test_known_symbol_resolved_without_api(self, client):
        """Known symbols resolve from the hardcoded map, no API call."""
        coin_id = client._resolve_coin_id("BTC")
        assert coin_id == "bitcoin"

    def test_case_insensitive_resolution(self, client):
        """Symbol resolution is case-insensitive."""
        assert client._resolve_coin_id("btc") == "bitcoin"
        assert client._resolve_coin_id("Eth") == "ethereum"

    def test_unknown_symbol_resolved_via_search(self, client):
        """Unknown symbols are resolved via the /search endpoint."""
        search_response = {
            "coins": [
                {"id": "some-token", "symbol": "NEWCOIN", "market_cap_rank": 50},
                {"id": "another-token", "symbol": "NEWCOIN", "market_cap_rank": 200},
            ]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = search_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response):
            coin_id = client._resolve_coin_id("NEWCOIN")

        assert coin_id == "some-token"  # Picks best market_cap_rank

    def test_unknown_symbol_picks_best_rank(self, client):
        """When multiple results match, pick the one with best rank."""
        search_response = {
            "coins": [
                {"id": "low-rank", "symbol": "XYZ", "market_cap_rank": 500},
                {"id": "high-rank", "symbol": "XYZ", "market_cap_rank": 10},
            ]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = search_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response):
            coin_id = client._resolve_coin_id("XYZ")

        assert coin_id == "high-rank"

    def test_unknown_symbol_no_results(self, client):
        """Returns None when search yields no results."""
        search_response = {"coins": []}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = search_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response):
            coin_id = client._resolve_coin_id("FAKECOIN")

        assert coin_id is None

    def test_unknown_symbol_no_matching_symbol(self, client):
        """Returns None when search results don't match the symbol."""
        search_response = {
            "coins": [
                {"id": "other-coin", "symbol": "OTHER", "market_cap_rank": 10},
            ]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = search_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response):
            coin_id = client._resolve_coin_id("MINE")

        assert coin_id is None

    def test_resolution_cached(self, client):
        """Once resolved, the coin ID is cached and not re-fetched."""
        search_response = {
            "coins": [
                {"id": "cached-coin", "symbol": "CACHE", "market_cap_rank": 1},
            ]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = search_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response) as mock_req:
            client._resolve_coin_id("CACHE")
            client._resolve_coin_id("CACHE")  # Second call should use cache

        mock_req.assert_called_once()  # Only one API call

    def test_resolution_failure_returns_none(self, client):
        """API failure during resolution returns None."""
        with patch.object(
            client._client, "request", side_effect=Exception("network error")
        ):
            coin_id = client._resolve_coin_id("BROKEN")

        assert coin_id is None

    def test_fallback_to_first_exact_match_without_rank(self, client):
        """Falls back to first exact symbol match when no rank available."""
        search_response = {
            "coins": [
                {"id": "no-rank-coin", "symbol": "NORANK"},
            ]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = search_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response):
            coin_id = client._resolve_coin_id("NORANK")

        assert coin_id == "no-rank-coin"


class TestGetPriceHistory:
    def test_single_symbol_daily_prices(self, client):
        """Fetches daily prices for a single known symbol."""
        chart_data = _make_market_chart_response([
            [_ts_ms(2024, 1, 15, 0), 42000.0],
            [_ts_ms(2024, 1, 15, 12), 42500.0],
            [_ts_ms(2024, 1, 16, 0), 43000.0],
            [_ts_ms(2024, 1, 16, 12), 43500.0],
        ])
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = chart_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response):
            result = client.get_price_history(
                ["BTC"], date(2024, 1, 15), date(2024, 1, 16)
            )

        assert len(result["BTC"]) == 2
        # Last price of Jan 15 is 42500
        assert result["BTC"][0].price_date == date(2024, 1, 15)
        assert result["BTC"][0].close_price == Decimal("42500.0")
        assert result["BTC"][0].source == "coingecko"
        assert result["BTC"][0].symbol == "BTC"
        # Last price of Jan 16 is 43500
        assert result["BTC"][1].price_date == date(2024, 1, 16)
        assert result["BTC"][1].close_price == Decimal("43500.0")

    def test_hourly_to_daily_picks_last_price(self, client):
        """For hourly data, picks the last data point per calendar day."""
        chart_data = _make_market_chart_response([
            [_ts_ms(2024, 1, 15, 0), 100.0],
            [_ts_ms(2024, 1, 15, 6), 101.0],
            [_ts_ms(2024, 1, 15, 12), 102.0],
            [_ts_ms(2024, 1, 15, 18), 103.0],
            [_ts_ms(2024, 1, 15, 23), 104.0],
        ])
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = chart_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response):
            result = client.get_price_history(
                ["ETH"], date(2024, 1, 15), date(2024, 1, 15)
            )

        assert len(result["ETH"]) == 1
        assert result["ETH"][0].close_price == Decimal("104.0")

    def test_empty_symbols_returns_empty_dict(self, client):
        """Empty symbol list returns empty dict without API call."""
        result = client.get_price_history([], date(2024, 1, 15), date(2024, 1, 15))
        assert result == {}

    def test_unknown_symbol_returns_empty_list(self, client):
        """Symbol that can't be resolved returns empty list."""
        search_response = {"coins": []}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = search_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response):
            result = client.get_price_history(
                ["NOSUCHCOIN"], date(2024, 1, 15), date(2024, 1, 15)
            )

        assert result["NOSUCHCOIN"] == []

    def test_api_failure_returns_empty_list(self, client):
        """API failure for price fetch returns empty list for that symbol."""
        # First call resolves (BTC is known), second call fails
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )

        with patch.object(client._client, "request", return_value=mock_response):
            result = client.get_price_history(
                ["BTC"], date(2024, 1, 15), date(2024, 1, 15)
            )

        assert result["BTC"] == []

    def test_no_price_data_returns_empty_list(self, client):
        """Empty prices array returns empty list."""
        chart_data = _make_market_chart_response([])
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = chart_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response):
            result = client.get_price_history(
                ["BTC"], date(2024, 1, 15), date(2024, 1, 15)
            )

        assert result["BTC"] == []

    def test_filters_prices_to_date_range(self, client):
        """Only returns prices within the requested date range."""
        chart_data = _make_market_chart_response([
            [_ts_ms(2024, 1, 14, 12), 41000.0],  # Before range
            [_ts_ms(2024, 1, 15, 12), 42000.0],  # In range
            [_ts_ms(2024, 1, 16, 12), 43000.0],  # In range
            [_ts_ms(2024, 1, 17, 12), 44000.0],  # After range
        ])
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = chart_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "request", return_value=mock_response):
            result = client.get_price_history(
                ["BTC"], date(2024, 1, 15), date(2024, 1, 16)
            )

        assert len(result["BTC"]) == 2
        dates = [pr.price_date for pr in result["BTC"]]
        assert date(2024, 1, 14) not in dates
        assert date(2024, 1, 17) not in dates

    def test_multiple_symbols(self, client):
        """Fetches prices for multiple symbols independently."""
        btc_data = _make_market_chart_response([
            [_ts_ms(2024, 1, 15, 12), 42000.0],
        ])
        eth_data = _make_market_chart_response([
            [_ts_ms(2024, 1, 15, 12), 2500.0],
        ])

        call_count = 0

        def mock_request(method, path, **kwargs):
            nonlocal call_count
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            if "/coins/bitcoin/" in path:
                mock_resp.json.return_value = btc_data
            elif "/coins/ethereum/" in path:
                mock_resp.json.return_value = eth_data
            else:
                mock_resp.json.return_value = {"prices": []}
            call_count += 1
            return mock_resp

        with patch.object(client._client, "request", side_effect=mock_request):
            result = client.get_price_history(
                ["BTC", "ETH"], date(2024, 1, 15), date(2024, 1, 15)
            )

        assert len(result["BTC"]) == 1
        assert result["BTC"][0].close_price == Decimal("42000.0")
        assert len(result["ETH"]) == 1
        assert result["ETH"][0].close_price == Decimal("2500.0")


class TestRateLimiting:
    def test_retries_on_429(self, client):
        """Retries with backoff on 429 rate limit responses."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = _make_market_chart_response([
            [_ts_ms(2024, 1, 15, 12), 42000.0],
        ])
        success_response.raise_for_status = MagicMock()

        with patch.object(
            client._client, "request",
            side_effect=[rate_limit_response, success_response],
        ):
            with patch("integrations.coingecko_client.time_module.sleep"):
                result = client.get_price_history(
                    ["BTC"], date(2024, 1, 15), date(2024, 1, 15)
                )

        assert len(result["BTC"]) == 1


class TestApiKey:
    def test_api_key_in_headers(self):
        """API key is sent as x-cg-demo-api-key header."""
        client = CoinGeckoClient(api_key="my-key")
        assert client._client.headers.get("x-cg-demo-api-key") == "my-key"

    def test_no_api_key_no_header(self):
        """No API key means no auth header."""
        client = CoinGeckoClient()
        assert "x-cg-demo-api-key" not in client._client.headers
