"""Yahoo Finance integration tests (real API calls).

These tests hit the Yahoo Finance API and are excluded by default.
Run with: pytest -m yahoo
"""

from datetime import date

import pytest


@pytest.mark.yahoo
class TestSingleSymbolSingleDate:
    def test_returns_price_for_known_symbol(self, yahoo_client):
        result = yahoo_client.get_price_history(
            ["AAPL"], date(2024, 1, 16), date(2024, 1, 16)
        )
        assert len(result["AAPL"]) == 1
        pr = result["AAPL"][0]
        assert pr.symbol == "AAPL"
        assert pr.source == "yahoo"
        assert pr.close_price > 0


@pytest.mark.yahoo
class TestMultiSymbolSingleDate:
    def test_returns_prices_for_multiple_symbols(self, yahoo_client):
        result = yahoo_client.get_price_history(
            ["AAPL", "MSFT"], date(2024, 1, 16), date(2024, 1, 16)
        )
        assert len(result["AAPL"]) == 1
        assert len(result["MSFT"]) == 1


@pytest.mark.yahoo
class TestWeekendDate:
    def test_weekend_returns_prior_friday(self, yahoo_client):
        # 2024-01-13 is Saturday, 2024-01-12 is Friday
        result = yahoo_client.get_price_history(
            ["AAPL"], date(2024, 1, 13), date(2024, 1, 13)
        )
        assert len(result["AAPL"]) == 1
        assert result["AAPL"][0].price_date == date(2024, 1, 12)


@pytest.mark.yahoo
class TestDateRange:
    def test_returns_expected_trading_days(self, yahoo_client):
        # 2024-01-15 (Mon) to 2024-01-19 (Fri) — 5 trading days
        # MLK Day is 2024-01-15, so 4 trading days expected
        result = yahoo_client.get_price_history(
            ["AAPL", "MSFT"], date(2024, 1, 15), date(2024, 1, 19)
        )
        # At least some results for each symbol
        assert len(result["AAPL"]) >= 3
        assert len(result["MSFT"]) >= 3


@pytest.mark.yahoo
class TestCryptoSymbols:
    def test_single_crypto_returns_price(self, yahoo_client):
        result = yahoo_client.get_price_history(
            ["BTC"], date(2024, 1, 16), date(2024, 1, 16)
        )
        assert len(result["BTC"]) == 1
        assert result["BTC"][0].symbol == "BTC"
        assert result["BTC"][0].close_price > 0

    def test_all_supported_cryptos(self, yahoo_client):
        result = yahoo_client.get_price_history(
            ["BTC", "ETH", "SOL", "SUI", "DOGE"],
            date(2024, 1, 16),
            date(2024, 1, 16),
        )
        for sym in ["BTC", "ETH", "SOL", "SUI", "DOGE"]:
            assert len(result[sym]) == 1, f"{sym} missing"
            assert result[sym][0].symbol == sym

    def test_mixed_crypto_and_equity(self, yahoo_client):
        result = yahoo_client.get_price_history(
            ["BTC", "AAPL"], date(2024, 1, 16), date(2024, 1, 16)
        )
        assert len(result["BTC"]) == 1
        assert len(result["AAPL"]) == 1
        assert result["BTC"][0].symbol == "BTC"
        assert result["AAPL"][0].symbol == "AAPL"
