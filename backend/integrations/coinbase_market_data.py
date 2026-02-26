"""Coinbase market data provider for cryptocurrency prices.

Uses the Coinbase Advanced Trade API (via CoinbaseClient) to fetch
daily candle data for crypto symbols. This replaces CoinGecko as the
primary crypto pricing provider when Coinbase credentials are configured.
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from integrations.market_data_protocol import PriceResult

logger = logging.getLogger(__name__)

# Maximum candles per request (Coinbase API limit)
_MAX_CANDLES = 300


class CoinbaseMarketDataProvider:
    """Market data provider using the Coinbase Advanced Trade API.

    Fetches daily OHLCV candle data for crypto symbols via an authenticated
    CoinbaseClient instance. Each ticker is mapped to a Coinbase product ID
    (e.g., ``BTC`` → ``BTC-USD``) and queried independently so a failure on
    one symbol does not block others.
    """

    def __init__(self, coinbase_client):
        """Initialize with an existing CoinbaseClient.

        Args:
            coinbase_client: A ``CoinbaseClient`` instance whose
                ``_get_client()`` returns an authenticated ``RESTClient``.
        """
        self._coinbase_client = coinbase_client

    @property
    def provider_name(self) -> str:
        return "coinbase"

    @staticmethod
    def _to_product_id(ticker: str) -> str:
        """Map a bare crypto ticker to a Coinbase product ID."""
        return f"{ticker.upper()}-USD"

    def get_price_history(
        self, symbols: list[str], start_date: date, end_date: date
    ) -> dict[str, list[PriceResult]]:
        """Fetch daily close prices from Coinbase candle data.

        Args:
            symbols: Crypto ticker symbols (e.g., ``["BTC", "ETH"]``).
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            Dict mapping each symbol to its list of daily ``PriceResult``
            objects. Symbols that fail return an empty list.
        """
        if not symbols:
            return {}

        logger.info(
            "Coinbase: fetching prices for %d symbols (%s to %s)",
            len(symbols), start_date, end_date,
        )

        rest_client = self._coinbase_client._get_client()

        start_ts = str(
            int(datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        )
        end_ts = str(
            int(datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc).timestamp())
        )

        result: dict[str, list[PriceResult]] = {s: [] for s in symbols}

        for symbol in symbols:
            product_id = self._to_product_id(symbol)
            try:
                response = rest_client.get_candles(
                    product_id=product_id,
                    start=start_ts,
                    end=end_ts,
                    granularity="ONE_DAY",
                )

                candles = response.candles if hasattr(response, "candles") else []
                if not candles:
                    logger.warning("Coinbase: no candle data for %s", product_id)
                    continue

                for candle in candles:
                    close_raw = getattr(candle, "close", None)
                    start_raw = getattr(candle, "start", None)
                    if close_raw is None or start_raw is None:
                        continue

                    try:
                        close_price = Decimal(str(close_raw))
                    except (InvalidOperation, ValueError):
                        continue

                    try:
                        candle_date = datetime.fromtimestamp(
                            int(start_raw), tz=timezone.utc
                        ).date()
                    except (ValueError, OSError):
                        continue

                    if start_date <= candle_date <= end_date:
                        result[symbol].append(
                            PriceResult(
                                symbol=symbol,
                                price_date=candle_date,
                                close_price=close_price,
                                source="coinbase",
                            )
                        )

                # Sort by date (candles may arrive in reverse chronological order)
                result[symbol].sort(key=lambda pr: pr.price_date)

            except Exception:
                logger.warning(
                    "Coinbase: failed to fetch prices for %s",
                    product_id, exc_info=True,
                )

        return result
