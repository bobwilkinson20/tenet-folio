"""CoinGecko market data provider for cryptocurrency prices."""

import logging
import time as time_module
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from integrations.market_data_protocol import PriceResult

logger = logging.getLogger(__name__)

# Hardcoded mapping for the most common crypto symbols.
# Covers the vast majority of real portfolios without an API call.
_KNOWN_COIN_IDS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "SUI": "sui",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "XRP": "ripple",
    "DOT": "polkadot",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "POL": "matic-network",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "LTC": "litecoin",
    "NEAR": "near",
    "APT": "aptos",
    "ARB": "arbitrum",
    "OP": "optimism",
    "FIL": "filecoin",
    "AAVE": "aave",
    "MKR": "maker",
    "SHIB": "shiba-inu",
    "XLM": "stellar",
    "ALGO": "algorand",
    "FTM": "fantom",
    "PEPE": "pepe",
    "RENDER": "render-token",
    "INJ": "injective-protocol",
    "SEI": "sei-network",
}

# Max retries for rate-limited requests
_MAX_RETRIES = 3
_BASE_DELAY_SECONDS = 1.0


class CoinGeckoClient:
    """Market data provider using the CoinGecko API for crypto prices."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with optional API key.

        Args:
            api_key: CoinGecko demo API key. If provided, uses the
                     x-cg-demo-api-key header for higher rate limits.
                     If None, uses the keyless public API.
        """
        headers: dict[str, str] = {}
        if api_key:
            headers["x-cg-demo-api-key"] = api_key
        self._client = httpx.Client(
            base_url="https://api.coingecko.com/api/v3",
            headers=headers,
            timeout=30.0,
        )
        self._resolved_ids: dict[str, str] = dict(_KNOWN_COIN_IDS)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    @property
    def provider_name(self) -> str:
        return "coingecko"

    def _resolve_coin_id(self, symbol: str) -> Optional[str]:
        """Resolve a ticker symbol to a CoinGecko coin ID.

        Checks the cached mapping first, then falls back to the
        /search endpoint for unknown symbols.
        """
        upper = symbol.upper()
        if upper in self._resolved_ids:
            return self._resolved_ids[upper]

        # Search CoinGecko for the symbol
        try:
            response = self._request_with_retry("GET", "/search", params={"query": symbol})
            data = response.json()
            coins = data.get("coins", [])
            if not coins:
                logger.warning(
                    "CoinGecko: no results for symbol %s", symbol
                )
                return None

            # Pick the coin with the best (lowest) market_cap_rank
            best = None
            for coin in coins:
                if coin.get("symbol", "").upper() != upper:
                    continue
                rank = coin.get("market_cap_rank")
                if rank is not None and (best is None or rank < best.get("market_cap_rank", float("inf"))):
                    best = coin

            # If no exact symbol match with rank, fall back to first exact match
            if best is None:
                for coin in coins:
                    if coin.get("symbol", "").upper() == upper:
                        best = coin
                        break

            if best is None:
                logger.warning(
                    "CoinGecko: no matching coin for symbol %s", symbol
                )
                return None

            coin_id = best["id"]
            self._resolved_ids[upper] = coin_id
            logger.info(
                "CoinGecko: resolved %s -> %s", symbol, coin_id
            )
            return coin_id

        except Exception:
            logger.warning(
                "CoinGecko: failed to resolve symbol %s", symbol,
                exc_info=True,
            )
            return None

    def _request_with_retry(
        self, method: str, path: str, **kwargs
    ) -> httpx.Response:
        """Make an HTTP request with retry on 429 rate limit responses."""
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._client.request(method, path, **kwargs)
                if response.status_code == 429:
                    delay = _BASE_DELAY_SECONDS * (2 ** attempt)
                    logger.warning(
                        "CoinGecko: rate limited, retrying in %.1fs (attempt %d/%d)",
                        delay, attempt + 1, _MAX_RETRIES,
                    )
                    time_module.sleep(delay)
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    delay = _BASE_DELAY_SECONDS * (2 ** attempt)
                    logger.warning(
                        "CoinGecko: rate limited, retrying in %.1fs (attempt %d/%d)",
                        delay, attempt + 1, _MAX_RETRIES,
                    )
                    time_module.sleep(delay)
                    last_exc = e
                    continue
                raise
            except Exception as e:
                last_exc = e
                raise

        raise last_exc or Exception("CoinGecko: max retries exceeded")

    def get_price_history(
        self, symbols: list[str], start_date: date, end_date: date
    ) -> dict[str, list[PriceResult]]:
        """Fetch historical crypto prices from CoinGecko.

        Args:
            symbols: List of crypto ticker symbols (e.g., ["BTC", "ETH"]).
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            Dict mapping each symbol to its list of daily PriceResults.
        """
        if not symbols:
            return {}

        logger.info(
            "CoinGecko: fetching prices for %d symbols (%s to %s)",
            len(symbols), start_date, end_date,
        )

        result: dict[str, list[PriceResult]] = {s: [] for s in symbols}

        # Convert dates to unix timestamps
        from_ts = int(datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        # Add a day to end_date to make it inclusive
        to_ts = int(datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc).timestamp())

        for symbol in symbols:
            coin_id = self._resolve_coin_id(symbol)
            if coin_id is None:
                continue

            try:
                response = self._request_with_retry(
                    "GET",
                    f"/coins/{coin_id}/market_chart/range",
                    params={
                        "vs_currency": "usd",
                        "from": str(from_ts),
                        "to": str(to_ts),
                    },
                )
                data = response.json()
                prices = data.get("prices", [])

                if not prices:
                    logger.warning(
                        "CoinGecko: no price data for %s (%s)", symbol, coin_id
                    )
                    continue

                # CoinGecko returns [[timestamp_ms, price], ...]
                # For ranges < 90 days, data is hourly — pick last price per day
                daily_prices: dict[date, Decimal] = {}
                for timestamp_ms, price in prices:
                    price_date = datetime.fromtimestamp(
                        timestamp_ms / 1000, tz=timezone.utc
                    ).date()
                    # Keep overwriting — last data point per day becomes the "close"
                    daily_prices[price_date] = Decimal(str(round(float(price), 6)))

                for price_date, close_price in sorted(daily_prices.items()):
                    if start_date <= price_date <= end_date:
                        result[symbol].append(
                            PriceResult(
                                symbol=symbol,
                                price_date=price_date,
                                close_price=close_price,
                                source="coingecko",
                            )
                        )

            except Exception:
                logger.warning(
                    "CoinGecko: failed to fetch prices for %s (%s)",
                    symbol, coin_id, exc_info=True,
                )

        return result
