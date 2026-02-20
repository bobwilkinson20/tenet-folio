"""Yahoo Finance market data provider implementation."""

import logging
from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf

from integrations.market_data_protocol import PriceResult

logger = logging.getLogger(__name__)


class YahooFinanceClient:
    """Market data provider using Yahoo Finance (yfinance library).

    Handles equities, ETFs, and other traditional securities.
    Crypto symbols are routed to a dedicated crypto provider
    (e.g., CoinGecko) by the MarketDataService.
    """

    @property
    def provider_name(self) -> str:
        return "yahoo"

    def get_price_history(
        self, symbols: list[str], start_date: date, end_date: date
    ) -> dict[str, list[PriceResult]]:
        """Fetch historical closing prices from Yahoo Finance.

        For single-date requests (start == end), uses a 10-day lookback
        to handle weekends and holidays, returning only the most recent
        close on or before the requested date.

        Args:
            symbols: List of ticker symbols.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            Dict mapping each symbol to its list of PriceResults.
        """
        if not symbols:
            return {}

        logger.info(
            "Yahoo Finance: fetching prices for %d symbols (%s to %s)",
            len(symbols), start_date, end_date,
        )

        result: dict[str, list[PriceResult]] = {s: [] for s in symbols}

        single_date = start_date == end_date
        if single_date:
            download_start = start_date - timedelta(days=10)
        else:
            download_start = start_date

        # yfinance end is exclusive, so add one day
        download_end = end_date + timedelta(days=1)

        try:
            df = yf.download(
                tickers=symbols,
                start=download_start.isoformat(),
                end=download_end.isoformat(),
                auto_adjust=True,
                progress=False,
            )
        except Exception:
            logger.warning("yfinance download failed for %s", symbols, exc_info=True)
            return result

        if df.empty:
            return result

        multi_symbol = len(symbols) > 1

        for symbol in symbols:
            try:
                if multi_symbol:
                    # MultiIndex columns: (metric, symbol)
                    if ("Close", symbol) not in df.columns:
                        continue
                    closes = df[("Close", symbol)].dropna()
                else:
                    # Flat columns for single symbol
                    if "Close" not in df.columns:
                        continue
                    closes = df["Close"].dropna()

                if closes.empty:
                    continue

                if single_date:
                    # Return only the most recent close on or before end_date
                    filtered = closes[closes.index.date <= end_date]
                    if filtered.empty:
                        continue
                    last = filtered.iloc[-1]
                    last_date = filtered.index[-1].date()
                    result[symbol].append(
                        PriceResult(
                            symbol=symbol,
                            price_date=last_date,
                            close_price=Decimal(str(round(float(last), 6))),
                            source="yahoo",
                        )
                    )
                else:
                    for ts, price in closes.items():
                        result[symbol].append(
                            PriceResult(
                                symbol=symbol,
                                price_date=ts.date(),
                                close_price=Decimal(str(round(float(price), 6))),
                                source="yahoo",
                            )
                        )
            except Exception:
                logger.warning(
                    "Failed to parse prices for %s", symbol, exc_info=True
                )

        return result
