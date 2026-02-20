"""Market data provider protocol definitions.

Defines the interface for market data providers (price feeds).
This is separate from the ProviderClient protocol, which handles
portfolio sync (accounts, holdings, activities).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass
class PriceResult:
    """A single closing price for a symbol on a specific date."""

    symbol: str
    price_date: date  # Actual trading date (may differ from requested for weekends/holidays)
    close_price: Decimal
    source: str  # e.g., "yahoo"


@dataclass
class Quote:
    """Live quote data. Defined for future extensibility — not used in v1."""

    symbol: str
    last_price: Decimal
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume: int | None = None


class MarketDataProvider(Protocol):
    """Protocol for market data providers.

    Implementations fetch price data from external sources.
    """

    @property
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'yahoo')."""
        ...

    def get_price_history(
        self, symbols: list[str], start_date: date, end_date: date
    ) -> dict[str, list[PriceResult]]:
        """Fetch historical closing prices for the given symbols and date range.

        Args:
            symbols: List of ticker symbols.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            Dict mapping each symbol to its list of daily closing prices.
            Unknown or failed symbols map to an empty list.
        """
        ...
