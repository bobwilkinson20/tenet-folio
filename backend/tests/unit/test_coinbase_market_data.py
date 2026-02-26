"""Unit tests for CoinbaseMarketDataProvider."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from integrations.coinbase_market_data import (
    CoinbaseMarketDataProvider,
    _MAX_CANDLES_PER_REQUEST,
)


def _make_candle(start_ts: int, close: str) -> MagicMock:
    """Create a mock Candle object matching the SDK structure."""
    candle = MagicMock()
    candle.start = str(start_ts)
    candle.close = close
    candle.open = close
    candle.high = close
    candle.low = close
    candle.volume = "100"
    return candle


def _make_candles_response(candles: list) -> MagicMock:
    """Create a mock GetProductCandlesResponse."""
    response = MagicMock()
    response.candles = candles
    return response


class TestProviderName:
    def test_provider_name_returns_coinbase(self):
        client = MagicMock()
        provider = CoinbaseMarketDataProvider(client)
        assert provider.provider_name == "coinbase"


class TestProductIdMapping:
    def test_btc_maps_to_btc_usd(self):
        assert CoinbaseMarketDataProvider._to_product_id("BTC") == "BTC-USD"

    def test_eth_maps_to_eth_usd(self):
        assert CoinbaseMarketDataProvider._to_product_id("ETH") == "ETH-USD"

    def test_lowercase_normalized_to_uppercase(self):
        assert CoinbaseMarketDataProvider._to_product_id("sol") == "SOL-USD"


class TestGetPriceHistory:
    def test_single_symbol_returns_correct_price_result(self):
        """Single symbol returns PriceResult with daily close."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        # Jan 15, 2024 00:00 UTC = 1705276800
        candle = _make_candle(1705276800, "42000.50")
        rest_client.get_candles.return_value = _make_candles_response([candle])

        provider = CoinbaseMarketDataProvider(mock_client)
        result = provider.get_price_history(
            ["BTC"], date(2024, 1, 15), date(2024, 1, 15)
        )

        assert len(result["BTC"]) == 1
        assert result["BTC"][0].symbol == "BTC"
        assert result["BTC"][0].price_date == date(2024, 1, 15)
        assert result["BTC"][0].close_price == Decimal("42000.50")
        assert result["BTC"][0].source == "coinbase"

        rest_client.get_candles.assert_called_once()
        call_kwargs = rest_client.get_candles.call_args
        assert call_kwargs.kwargs["product_id"] == "BTC-USD"
        assert call_kwargs.kwargs["granularity"] == "ONE_DAY"

    def test_multiple_symbols_fetched_independently(self):
        """Each symbol triggers its own get_candles call."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        btc_candle = _make_candle(1705276800, "42000.00")
        eth_candle = _make_candle(1705276800, "2500.00")

        def side_effect(**kwargs):
            if kwargs["product_id"] == "BTC-USD":
                return _make_candles_response([btc_candle])
            elif kwargs["product_id"] == "ETH-USD":
                return _make_candles_response([eth_candle])
            return _make_candles_response([])

        rest_client.get_candles.side_effect = side_effect

        provider = CoinbaseMarketDataProvider(mock_client)
        result = provider.get_price_history(
            ["BTC", "ETH"], date(2024, 1, 15), date(2024, 1, 15)
        )

        assert len(result["BTC"]) == 1
        assert result["BTC"][0].close_price == Decimal("42000.00")
        assert len(result["ETH"]) == 1
        assert result["ETH"][0].close_price == Decimal("2500.00")
        assert rest_client.get_candles.call_count == 2

    def test_multi_day_range_returns_multiple_results(self):
        """Multiple candles over a date range are all returned."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        candles = [
            _make_candle(1705276800, "42000.00"),   # Jan 15
            _make_candle(1705363200, "42500.00"),   # Jan 16
            _make_candle(1705449600, "43000.00"),   # Jan 17
        ]
        rest_client.get_candles.return_value = _make_candles_response(candles)

        provider = CoinbaseMarketDataProvider(mock_client)
        result = provider.get_price_history(
            ["BTC"], date(2024, 1, 15), date(2024, 1, 17)
        )

        assert len(result["BTC"]) == 3
        assert result["BTC"][0].price_date == date(2024, 1, 15)
        assert result["BTC"][2].price_date == date(2024, 1, 17)

    def test_candles_sorted_by_date(self):
        """Candles returned in reverse order are sorted chronologically."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        # Return candles in reverse order (newest first)
        candles = [
            _make_candle(1705449600, "43000.00"),   # Jan 17
            _make_candle(1705276800, "42000.00"),   # Jan 15
            _make_candle(1705363200, "42500.00"),   # Jan 16
        ]
        rest_client.get_candles.return_value = _make_candles_response(candles)

        provider = CoinbaseMarketDataProvider(mock_client)
        result = provider.get_price_history(
            ["BTC"], date(2024, 1, 15), date(2024, 1, 17)
        )

        dates = [pr.price_date for pr in result["BTC"]]
        assert dates == [date(2024, 1, 15), date(2024, 1, 16), date(2024, 1, 17)]


class TestErrorHandling:
    def test_failed_symbol_returns_empty_list(self):
        """API error on one symbol doesn't block others."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        eth_candle = _make_candle(1705276800, "2500.00")

        def side_effect(**kwargs):
            if kwargs["product_id"] == "BTC-USD":
                raise Exception("API error")
            return _make_candles_response([eth_candle])

        rest_client.get_candles.side_effect = side_effect

        provider = CoinbaseMarketDataProvider(mock_client)
        result = provider.get_price_history(
            ["BTC", "ETH"], date(2024, 1, 15), date(2024, 1, 15)
        )

        assert result["BTC"] == []
        assert len(result["ETH"]) == 1
        assert result["ETH"][0].close_price == Decimal("2500.00")

    def test_empty_candles_response(self):
        """Empty candle response for a symbol returns empty list."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        rest_client.get_candles.return_value = _make_candles_response([])

        provider = CoinbaseMarketDataProvider(mock_client)
        result = provider.get_price_history(
            ["BTC"], date(2024, 1, 15), date(2024, 1, 15)
        )

        assert result["BTC"] == []

    def test_candle_with_invalid_close_price_skipped(self):
        """Candle with non-numeric close is silently skipped."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        bad_candle = _make_candle(1705276800, "not_a_number")
        good_candle = _make_candle(1705363200, "42000.00")
        rest_client.get_candles.return_value = _make_candles_response(
            [bad_candle, good_candle]
        )

        provider = CoinbaseMarketDataProvider(mock_client)
        result = provider.get_price_history(
            ["BTC"], date(2024, 1, 15), date(2024, 1, 16)
        )

        assert len(result["BTC"]) == 1
        assert result["BTC"][0].price_date == date(2024, 1, 16)

    def test_candle_with_none_close_skipped(self):
        """Candle with None close is skipped."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        candle = MagicMock()
        candle.start = "1705276800"
        candle.close = None
        rest_client.get_candles.return_value = _make_candles_response([candle])

        provider = CoinbaseMarketDataProvider(mock_client)
        result = provider.get_price_history(
            ["BTC"], date(2024, 1, 15), date(2024, 1, 15)
        )

        assert result["BTC"] == []

    def test_candle_outside_date_range_excluded(self):
        """Candles outside the requested date range are filtered out."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        # Jan 14 (before range) and Jan 15 (in range)
        candles = [
            _make_candle(1705190400, "41000.00"),   # Jan 14
            _make_candle(1705276800, "42000.00"),   # Jan 15
        ]
        rest_client.get_candles.return_value = _make_candles_response(candles)

        provider = CoinbaseMarketDataProvider(mock_client)
        result = provider.get_price_history(
            ["BTC"], date(2024, 1, 15), date(2024, 1, 15)
        )

        assert len(result["BTC"]) == 1
        assert result["BTC"][0].price_date == date(2024, 1, 15)


class TestEmptyInput:
    def test_empty_symbol_list_returns_empty_dict(self):
        mock_client = MagicMock()
        provider = CoinbaseMarketDataProvider(mock_client)

        result = provider.get_price_history([], date(2024, 1, 15), date(2024, 1, 15))

        assert result == {}
        mock_client._get_client.assert_not_called()


class TestChunking:
    """Tests for automatic chunking when date range exceeds API limit."""

    def test_short_range_uses_single_request(self):
        """A range within the limit makes exactly one API call."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        candle = _make_candle(1705276800, "42000.00")
        rest_client.get_candles.return_value = _make_candles_response([candle])

        provider = CoinbaseMarketDataProvider(mock_client)
        provider.get_price_history(["BTC"], date(2024, 1, 15), date(2024, 1, 15))

        assert rest_client.get_candles.call_count == 1

    def test_long_range_chunks_into_multiple_requests(self):
        """A range exceeding _MAX_CANDLES_PER_REQUEST splits into chunks."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        rest_client.get_candles.return_value = _make_candles_response([])

        provider = CoinbaseMarketDataProvider(mock_client)
        start = date(2024, 1, 1)
        # 400 days > 300 limit → should produce 2 chunks
        end = start + timedelta(days=399)
        provider.get_price_history(["BTC"], start, end)

        assert rest_client.get_candles.call_count == 2

    def test_exact_boundary_uses_single_request(self):
        """Exactly _MAX_CANDLES_PER_REQUEST days fits in one request."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        rest_client.get_candles.return_value = _make_candles_response([])

        provider = CoinbaseMarketDataProvider(mock_client)
        start = date(2024, 1, 1)
        end = start + timedelta(days=_MAX_CANDLES_PER_REQUEST - 1)
        provider.get_price_history(["BTC"], start, end)

        assert rest_client.get_candles.call_count == 1

    def test_one_over_boundary_uses_two_requests(self):
        """One day over the limit triggers a second request."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        rest_client.get_candles.return_value = _make_candles_response([])

        provider = CoinbaseMarketDataProvider(mock_client)
        start = date(2024, 1, 1)
        end = start + timedelta(days=_MAX_CANDLES_PER_REQUEST)
        provider.get_price_history(["BTC"], start, end)

        assert rest_client.get_candles.call_count == 2

    def test_chunked_results_are_merged(self):
        """Candles from multiple chunks are merged into one result list."""
        mock_client = MagicMock()
        rest_client = MagicMock()
        mock_client._get_client.return_value = rest_client

        # First chunk returns one candle, second returns another
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_candles_response([_make_candle(1704067200, "42000.00")])
            return _make_candles_response([_make_candle(1730073600, "70000.00")])

        rest_client.get_candles.side_effect = side_effect

        provider = CoinbaseMarketDataProvider(mock_client)
        start = date(2024, 1, 1)
        end = start + timedelta(days=399)  # 2 chunks
        result = provider.get_price_history(["BTC"], start, end)

        assert len(result["BTC"]) == 2
        assert result["BTC"][0].close_price == Decimal("42000.00")
        assert result["BTC"][1].close_price == Decimal("70000.00")
