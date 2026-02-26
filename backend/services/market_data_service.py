"""Market data service — thin orchestrator for market data providers."""

import logging
from datetime import date
from typing import Optional

from integrations.market_data_protocol import MarketDataProvider, PriceResult

logger = logging.getLogger(__name__)


class MarketDataService:
    """Orchestrates market data fetching via pluggable providers.

    Supports routing crypto symbols to a dedicated crypto provider
    (Coinbase) while sending equities to the default provider
    (Yahoo Finance). When Coinbase is not configured, all symbols
    — including crypto — are handled by Yahoo Finance.
    """

    def __init__(
        self,
        provider: Optional[MarketDataProvider] = None,
        crypto_provider: Optional[MarketDataProvider] = None,
    ):
        """Initialize with optional providers for dependency injection.

        Args:
            provider: Default market data provider (equities). If None,
                     a YahooFinanceClient is created on first use.
            crypto_provider: Crypto market data provider. If None,
                            a CoinbaseMarketDataProvider is created on
                            first use when Coinbase credentials are available.
                            Set to False (via _crypto_provider_checked) to
                            skip creation when credentials are unavailable.
        """
        self._provider = provider
        self._crypto_provider = crypto_provider
        # Track whether we've already attempted to create a crypto provider.
        # Avoids retrying credential loading on every call.
        self._crypto_provider_checked = crypto_provider is not None

    @property
    def provider(self) -> MarketDataProvider:
        """Get the default market data provider, creating if not provided."""
        if self._provider is None:
            from integrations.yahoo_finance_client import YahooFinanceClient

            self._provider = YahooFinanceClient()
        return self._provider

    @property
    def crypto_provider(self) -> Optional[MarketDataProvider]:
        """Get the crypto market data provider, or None if unavailable.

        Lazily attempts to create a CoinbaseMarketDataProvider using
        credentials from settings. Returns None when Coinbase is not
        configured, causing all symbols to route through Yahoo Finance.
        """
        if not self._crypto_provider_checked:
            self._crypto_provider_checked = True
            try:
                from integrations.coinbase_client import CoinbaseClient
                from integrations.coinbase_market_data import CoinbaseMarketDataProvider

                client = CoinbaseClient()
                if client.is_configured():
                    # Verify we can create the REST client
                    client._get_client()
                    self._crypto_provider = CoinbaseMarketDataProvider(client)
                    logger.info("Coinbase market data provider initialized for crypto pricing")
                else:
                    logger.info(
                        "Coinbase not configured; crypto prices will use Yahoo Finance"
                    )
            except Exception:
                logger.info(
                    "Coinbase market data provider unavailable; "
                    "crypto prices will use Yahoo Finance",
                    exc_info=True,
                )
        return self._crypto_provider

    def get_price_history(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        crypto_symbols: Optional[set[str]] = None,
    ) -> dict[str, list[PriceResult]]:
        """Fetch historical prices, normalizing symbols to uppercase.

        When crypto_symbols is provided and a crypto provider is available,
        splits the request: crypto symbols go to the crypto provider,
        everything else goes to the default provider. When no crypto
        provider is available, all symbols go through the default provider.

        Args:
            symbols: List of ticker symbols (case-insensitive).
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            crypto_symbols: Set of symbols classified as crypto. If None,
                           all symbols go to the default provider.

        Returns:
            Dict mapping each uppercase symbol to its list of PriceResults.
        """
        if not symbols:
            return {}

        normalized = [s.upper() for s in symbols]

        if crypto_symbols and self.crypto_provider is not None:
            crypto_upper = {s.upper() for s in crypto_symbols}
            crypto_list = [s for s in normalized if s in crypto_upper]
            equity_list = [s for s in normalized if s not in crypto_upper]
        else:
            crypto_list = []
            equity_list = normalized

        result: dict[str, list[PriceResult]] = {}

        # Fetch equity prices from default provider
        if equity_list:
            result.update(self.provider.get_price_history(equity_list, start_date, end_date))

        # Fetch crypto prices from crypto provider
        if crypto_list:
            result.update(self.crypto_provider.get_price_history(crypto_list, start_date, end_date))

        return result
