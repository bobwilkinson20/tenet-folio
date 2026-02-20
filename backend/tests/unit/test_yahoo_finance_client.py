"""Unit tests for YahooFinanceClient (mocked yfinance)."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from integrations.yahoo_finance_client import YahooFinanceClient


@pytest.fixture
def client():
    return YahooFinanceClient()


def _make_df(data: dict, dates: list[str]) -> pd.DataFrame:
    """Build a DataFrame with DatetimeIndex, mimicking yfinance output."""
    index = pd.DatetimeIndex(dates)
    return pd.DataFrame(data, index=index)


class TestSingleSymbolSingleDate:
    def test_returns_correct_price_result(self, client):
        df = _make_df({"Close": [150.25]}, ["2024-01-15"])
        with patch("yfinance.download", return_value=df) as mock_dl:
            result = client.get_price_history(["AAPL"], date(2024, 1, 15), date(2024, 1, 15))

        assert len(result["AAPL"]) == 1
        pr = result["AAPL"][0]
        assert pr.symbol == "AAPL"
        assert pr.price_date == date(2024, 1, 15)
        assert pr.close_price == Decimal("150.25")
        assert pr.source == "yahoo"
        mock_dl.assert_called_once()

    def test_unknown_symbol_returns_empty_list(self, client):
        df = pd.DataFrame()
        with patch("yfinance.download", return_value=df):
            result = client.get_price_history(["FAKE"], date(2024, 1, 15), date(2024, 1, 15))

        assert result["FAKE"] == []

    def test_weekend_date_returns_prior_friday(self, client):
        # Saturday requested — lookback window includes Friday
        df = _make_df({"Close": [148.0, 149.0, 150.0]}, ["2024-01-10", "2024-01-11", "2024-01-12"])
        with patch("yfinance.download", return_value=df):
            result = client.get_price_history(["AAPL"], date(2024, 1, 13), date(2024, 1, 13))

        assert len(result["AAPL"]) == 1
        assert result["AAPL"][0].price_date == date(2024, 1, 12)  # Friday


class TestMultiSymbolSingleDate:
    def test_returns_correct_dict(self, client):
        cols = pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Close", "MSFT")])
        data = [[150.25, 380.50]]
        index = pd.DatetimeIndex(["2024-01-15"])
        df = pd.DataFrame(data, index=index, columns=cols)

        with patch("yfinance.download", return_value=df):
            result = client.get_price_history(
                ["AAPL", "MSFT"], date(2024, 1, 15), date(2024, 1, 15)
            )

        assert len(result["AAPL"]) == 1
        assert len(result["MSFT"]) == 1
        assert result["AAPL"][0].close_price == Decimal("150.25")
        assert result["MSFT"][0].close_price == Decimal("380.5")


class TestMultiSymbolDateRange:
    def test_returns_dict_of_lists(self, client):
        cols = pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Close", "MSFT")])
        data = [
            [150.0, 380.0],
            [151.0, 381.0],
            [152.0, 382.0],
        ]
        index = pd.DatetimeIndex(["2024-01-15", "2024-01-16", "2024-01-17"])
        df = pd.DataFrame(data, index=index, columns=cols)

        with patch("yfinance.download", return_value=df):
            result = client.get_price_history(
                ["AAPL", "MSFT"], date(2024, 1, 15), date(2024, 1, 17)
            )

        assert len(result["AAPL"]) == 3
        assert len(result["MSFT"]) == 3
        assert result["AAPL"][0].price_date == date(2024, 1, 15)
        assert result["AAPL"][2].price_date == date(2024, 1, 17)


class TestErrorHandling:
    def test_download_exception_returns_empty_results(self, client):
        with patch("yfinance.download", side_effect=Exception("network error")):
            result = client.get_price_history(["AAPL"], date(2024, 1, 15), date(2024, 1, 15))

        assert result["AAPL"] == []

    def test_empty_symbols_returns_empty_dict(self, client):
        result = client.get_price_history([], date(2024, 1, 15), date(2024, 1, 15))
        assert result == {}


class TestDecimalPrecision:
    def test_preserves_precision(self, client):
        df = _make_df({"Close": [150.123456]}, ["2024-01-15"])
        with patch("yfinance.download", return_value=df):
            result = client.get_price_history(["AAPL"], date(2024, 1, 15), date(2024, 1, 15))

        assert result["AAPL"][0].close_price == Decimal("150.123456")


class TestProviderName:
    def test_provider_name(self, client):
        assert client.provider_name == "yahoo"
