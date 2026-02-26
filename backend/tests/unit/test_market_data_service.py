"""Unit tests for MarketDataService."""

from datetime import date
from decimal import Decimal

from integrations.market_data_protocol import PriceResult
from services.market_data_service import MarketDataService
from tests.fixtures.mocks import MockMarketDataProvider


SAMPLE_PRICES = {
    "AAPL": [
        PriceResult(
            symbol="AAPL",
            price_date=date(2024, 1, 15),
            close_price=Decimal("150.25"),
            source="mock",
        ),
    ],
    "MSFT": [
        PriceResult(
            symbol="MSFT",
            price_date=date(2024, 1, 15),
            close_price=Decimal("380.50"),
            source="mock",
        ),
    ],
}

SAMPLE_CRYPTO_PRICES = {
    "BTC": [
        PriceResult(
            symbol="BTC",
            price_date=date(2024, 1, 15),
            close_price=Decimal("42000.00"),
            source="mock_crypto",
        ),
    ],
    "ETH": [
        PriceResult(
            symbol="ETH",
            price_date=date(2024, 1, 15),
            close_price=Decimal("2500.00"),
            source="mock_crypto",
        ),
    ],
}

# Combined prices simulating Yahoo handling both equities and crypto
SAMPLE_ALL_PRICES = {**SAMPLE_PRICES, **{
    "BTC": [
        PriceResult(
            symbol="BTC",
            price_date=date(2024, 1, 15),
            close_price=Decimal("41999.00"),
            source="mock",
        ),
    ],
    "ETH": [
        PriceResult(
            symbol="ETH",
            price_date=date(2024, 1, 15),
            close_price=Decimal("2499.00"),
            source="mock",
        ),
    ],
}}


class TestDelegation:
    def test_delegates_to_provider_and_returns_result(self):
        provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        service = MarketDataService(provider=provider)

        result = service.get_price_history(["AAPL"], date(2024, 1, 15), date(2024, 1, 15))

        assert len(result["AAPL"]) == 1
        assert result["AAPL"][0].close_price == Decimal("150.25")

    def test_single_date_request_delegates_correctly(self):
        provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        service = MarketDataService(provider=provider)

        result = service.get_price_history(["AAPL", "MSFT"], date(2024, 1, 15), date(2024, 1, 15))

        assert "AAPL" in result
        assert "MSFT" in result

    def test_date_range_request_delegates_correctly(self):
        prices = {
            "AAPL": [
                PriceResult("AAPL", date(2024, 1, 15), Decimal("150"), "mock"),
                PriceResult("AAPL", date(2024, 1, 16), Decimal("151"), "mock"),
            ],
        }
        provider = MockMarketDataProvider(prices=prices)
        service = MarketDataService(provider=provider)

        result = service.get_price_history(["AAPL"], date(2024, 1, 15), date(2024, 1, 16))

        assert len(result["AAPL"]) == 2


class TestSymbolNormalization:
    def test_normalizes_symbols_to_uppercase(self):
        provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        service = MarketDataService(provider=provider)

        result = service.get_price_history(["aapl"], date(2024, 1, 15), date(2024, 1, 15))

        # Provider receives "AAPL" (uppercase)
        assert "AAPL" in result
        assert len(result["AAPL"]) == 1


class TestEdgeCases:
    def test_unknown_symbol_returns_empty_list(self):
        provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        service = MarketDataService(provider=provider)

        result = service.get_price_history(["FAKE"], date(2024, 1, 15), date(2024, 1, 15))

        assert result["FAKE"] == []

    def test_empty_symbol_list_returns_empty_dict(self):
        provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        service = MarketDataService(provider=provider)

        result = service.get_price_history([], date(2024, 1, 15), date(2024, 1, 15))

        assert result == {}


class TestCryptoRouting:
    """Tests for routing crypto symbols to a dedicated crypto provider."""

    def test_crypto_symbols_routed_to_crypto_provider(self):
        """Crypto symbols go to the crypto provider, not the default."""
        equity_provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        crypto_provider = MockMarketDataProvider(prices=SAMPLE_CRYPTO_PRICES)
        service = MarketDataService(provider=equity_provider, crypto_provider=crypto_provider)

        result = service.get_price_history(
            ["BTC"], date(2024, 1, 15), date(2024, 1, 15),
            crypto_symbols={"BTC"},
        )

        assert len(result["BTC"]) == 1
        assert result["BTC"][0].close_price == Decimal("42000.00")
        assert result["BTC"][0].source == "mock_crypto"

    def test_equities_not_routed_to_crypto_provider(self):
        """Non-crypto symbols go to the default provider."""
        equity_provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        crypto_provider = MockMarketDataProvider(prices=SAMPLE_CRYPTO_PRICES)
        service = MarketDataService(provider=equity_provider, crypto_provider=crypto_provider)

        result = service.get_price_history(
            ["AAPL"], date(2024, 1, 15), date(2024, 1, 15),
            crypto_symbols={"BTC"},
        )

        assert len(result["AAPL"]) == 1
        assert result["AAPL"][0].source == "mock"

    def test_mixed_crypto_and_equity(self):
        """Mixed symbols are split correctly between providers."""
        equity_provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        crypto_provider = MockMarketDataProvider(prices=SAMPLE_CRYPTO_PRICES)
        service = MarketDataService(provider=equity_provider, crypto_provider=crypto_provider)

        result = service.get_price_history(
            ["AAPL", "BTC", "MSFT", "ETH"],
            date(2024, 1, 15), date(2024, 1, 15),
            crypto_symbols={"BTC", "ETH"},
        )

        # Equities from default provider
        assert result["AAPL"][0].source == "mock"
        assert result["MSFT"][0].source == "mock"
        # Crypto from crypto provider
        assert result["BTC"][0].source == "mock_crypto"
        assert result["ETH"][0].source == "mock_crypto"

    def test_crypto_symbols_none_preserves_existing_behavior(self):
        """When crypto_symbols is None, all symbols go to default provider."""
        equity_provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        crypto_provider = MockMarketDataProvider(prices=SAMPLE_CRYPTO_PRICES)
        service = MarketDataService(provider=equity_provider, crypto_provider=crypto_provider)

        result = service.get_price_history(
            ["AAPL"], date(2024, 1, 15), date(2024, 1, 15),
            crypto_symbols=None,
        )

        assert len(result["AAPL"]) == 1
        assert result["AAPL"][0].source == "mock"

    def test_empty_crypto_symbols_set(self):
        """Empty crypto_symbols set sends everything to default provider."""
        equity_provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        crypto_provider = MockMarketDataProvider(prices=SAMPLE_CRYPTO_PRICES)
        service = MarketDataService(provider=equity_provider, crypto_provider=crypto_provider)

        result = service.get_price_history(
            ["AAPL"], date(2024, 1, 15), date(2024, 1, 15),
            crypto_symbols=set(),
        )

        assert len(result["AAPL"]) == 1
        assert result["AAPL"][0].source == "mock"

    def test_all_symbols_crypto(self):
        """When all symbols are crypto, nothing goes to default provider."""
        equity_provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        crypto_provider = MockMarketDataProvider(prices=SAMPLE_CRYPTO_PRICES)
        service = MarketDataService(provider=equity_provider, crypto_provider=crypto_provider)

        result = service.get_price_history(
            ["BTC", "ETH"], date(2024, 1, 15), date(2024, 1, 15),
            crypto_symbols={"BTC", "ETH"},
        )

        assert len(result["BTC"]) == 1
        assert len(result["ETH"]) == 1
        assert result["BTC"][0].source == "mock_crypto"
        assert result["ETH"][0].source == "mock_crypto"

    def test_crypto_routing_case_insensitive(self):
        """Crypto routing works with mixed-case input symbols."""
        equity_provider = MockMarketDataProvider(prices=SAMPLE_PRICES)
        crypto_provider = MockMarketDataProvider(prices=SAMPLE_CRYPTO_PRICES)
        service = MarketDataService(provider=equity_provider, crypto_provider=crypto_provider)

        result = service.get_price_history(
            ["btc"], date(2024, 1, 15), date(2024, 1, 15),
            crypto_symbols={"BTC"},
        )

        assert len(result["BTC"]) == 1
        assert result["BTC"][0].source == "mock_crypto"


class TestNoCryptoProvider:
    """Tests for behavior when no crypto provider is available."""

    def test_crypto_symbols_go_to_default_when_no_crypto_provider(self):
        """When crypto_provider is None, crypto symbols go through the default."""
        all_provider = MockMarketDataProvider(prices=SAMPLE_ALL_PRICES)
        service = MarketDataService(provider=all_provider, crypto_provider=None)
        # Mark as checked so it doesn't try to create a real one
        service._crypto_provider_checked = True

        result = service.get_price_history(
            ["BTC", "ETH"], date(2024, 1, 15), date(2024, 1, 15),
            crypto_symbols={"BTC", "ETH"},
        )

        assert len(result["BTC"]) == 1
        assert len(result["ETH"]) == 1
        # Should come from the default (mock) provider, not crypto
        assert result["BTC"][0].source == "mock"
        assert result["ETH"][0].source == "mock"

    def test_mixed_symbols_all_go_to_default_when_no_crypto_provider(self):
        """Mixed crypto+equity all go to default when no crypto provider."""
        all_provider = MockMarketDataProvider(prices=SAMPLE_ALL_PRICES)
        service = MarketDataService(provider=all_provider, crypto_provider=None)
        service._crypto_provider_checked = True

        result = service.get_price_history(
            ["AAPL", "BTC"], date(2024, 1, 15), date(2024, 1, 15),
            crypto_symbols={"BTC"},
        )

        assert len(result["AAPL"]) == 1
        assert len(result["BTC"]) == 1
        assert result["AAPL"][0].source == "mock"
        assert result["BTC"][0].source == "mock"

    def test_crypto_provider_property_returns_none_when_not_injected(self):
        """crypto_provider returns None when not injected and checked."""
        service = MarketDataService(provider=MockMarketDataProvider())
        service._crypto_provider_checked = True

        assert service.crypto_provider is None
