"""Market data API endpoints."""

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from services.market_data_service import MarketDataService

router = APIRouter(prefix="/api/market-data", tags=["market-data"])

# Dependency injection for testing
_market_data_service_override: Optional[MarketDataService] = None


def get_market_data_service() -> MarketDataService:
    """Get MarketDataService instance, allowing for test overrides."""
    if _market_data_service_override is not None:
        return _market_data_service_override
    return MarketDataService()


def set_market_data_service_override(service: Optional[MarketDataService]) -> None:
    """Set a MarketDataService override for testing."""
    global _market_data_service_override
    _market_data_service_override = service


class PriceResponse(BaseModel):
    """A single closing price for a symbol on a date."""

    symbol: str
    price_date: date
    close_price: Decimal
    source: str


class PriceHistoryResponse(BaseModel):
    """Price history for one or more symbols."""

    prices: dict[str, list[PriceResponse]]


@router.post("/history", response_model=PriceHistoryResponse)
def get_price_history(
    symbols: list[str],
    start: date = Query(..., description="Start date (inclusive)"),
    end: date = Query(..., description="End date (inclusive)"),
    service: MarketDataService = Depends(get_market_data_service),
):
    """Fetch historical closing prices for the given symbols.

    Symbols are passed in the request body as a JSON array.
    Date range is specified via query parameters.

    Returns dict mapping each symbol to its list of daily closes.
    Unknown symbols get an empty list.
    """
    results = service.get_price_history(symbols, start, end)
    return PriceHistoryResponse(
        prices={
            symbol: [
                PriceResponse(
                    symbol=pr.symbol,
                    price_date=pr.price_date,
                    close_price=pr.close_price,
                    source=pr.source,
                )
                for pr in price_list
            ]
            for symbol, price_list in results.items()
        }
    )
