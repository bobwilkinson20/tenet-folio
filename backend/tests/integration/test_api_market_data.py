"""Integration tests for market data API endpoints."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.market_data import get_market_data_service
from integrations.market_data_protocol import PriceResult
from main import app
from services.market_data_service import MarketDataService
from tests.fixtures.mocks import MockMarketDataProvider

SAMPLE_PRICES = {
    "AAPL": [
        PriceResult("AAPL", date(2024, 1, 15), Decimal("150.25"), "mock"),
    ],
    "MSFT": [
        PriceResult("MSFT", date(2024, 1, 15), Decimal("380.50"), "mock"),
        PriceResult("MSFT", date(2024, 1, 16), Decimal("382.00"), "mock"),
        PriceResult("MSFT", date(2024, 1, 17), Decimal("381.00"), "mock"),
    ],
}


@pytest.fixture
def market_client():
    """Create a test client with a mocked MarketDataService."""
    provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
    service = MarketDataService(provider=provider)

    def override():
        return service

    app.dependency_overrides[get_market_data_service] = override
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_market_data_service, None)


class TestSingleSymbolSingleDate:
    def test_returns_200_with_price(self, market_client):
        response = market_client.post(
            "/api/market-data/history?start=2024-01-15&end=2024-01-15",
            json=["AAPL"],
        )
        assert response.status_code == 200
        data = response.json()
        assert "AAPL" in data["prices"]
        assert len(data["prices"]["AAPL"]) == 1
        assert data["prices"]["AAPL"][0]["symbol"] == "AAPL"
        assert data["prices"]["AAPL"][0]["price_date"] == "2024-01-15"
        assert float(data["prices"]["AAPL"][0]["close_price"]) == 150.25
        assert data["prices"]["AAPL"][0]["source"] == "mock"


class TestMultiSymbolSingleDate:
    def test_returns_200_with_prices_for_both(self, market_client):
        response = market_client.post(
            "/api/market-data/history?start=2024-01-15&end=2024-01-15",
            json=["AAPL", "MSFT"],
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["prices"]["AAPL"]) == 1
        assert len(data["prices"]["MSFT"]) == 1


class TestMultiSymbolDateRange:
    def test_returns_200_with_date_range(self, market_client):
        response = market_client.post(
            "/api/market-data/history?start=2024-01-15&end=2024-01-17",
            json=["MSFT"],
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["prices"]["MSFT"]) == 3


class TestUnknownSymbol:
    def test_returns_empty_list_for_unknown(self, market_client):
        response = market_client.post(
            "/api/market-data/history?start=2024-01-15&end=2024-01-15",
            json=["FAKE"],
        )
        assert response.status_code == 200
        data = response.json()
        assert data["prices"]["FAKE"] == []


class TestEmptySymbols:
    def test_returns_empty_dict_for_empty_list(self, market_client):
        response = market_client.post(
            "/api/market-data/history?start=2024-01-15&end=2024-01-15",
            json=[],
        )
        assert response.status_code == 200
        data = response.json()
        assert data["prices"] == {}


class TestCaseInsensitive:
    def test_lowercase_symbols_normalized(self, market_client):
        response = market_client.post(
            "/api/market-data/history?start=2024-01-15&end=2024-01-15",
            json=["aapl"],
        )
        assert response.status_code == 200
        data = response.json()
        assert "AAPL" in data["prices"]
        assert len(data["prices"]["AAPL"]) == 1
