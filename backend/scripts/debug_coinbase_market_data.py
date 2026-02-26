#!/usr/bin/env python3
"""Debug script to test the Coinbase market data provider for crypto pricing.

Fetches daily close prices for a few crypto symbols via the Coinbase
Advanced Trade API candle endpoint. Useful for verifying that credentials
work and prices come back correctly.

Usage:
    cd backend
    uv run python -m scripts.debug_coinbase_market_data
    uv run python -m scripts.debug_coinbase_market_data BTC ETH SOL
    uv run python -m scripts.debug_coinbase_market_data --days 7 BTC
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.coinbase_client import CoinbaseClient
from integrations.coinbase_market_data import CoinbaseMarketDataProvider


DEFAULT_SYMBOLS = ["BTC", "ETH", "SOL"]


def main():
    parser = argparse.ArgumentParser(description="Test Coinbase crypto pricing")
    parser.add_argument(
        "symbols", nargs="*", default=DEFAULT_SYMBOLS,
        help=f"Crypto ticker symbols (default: {' '.join(DEFAULT_SYMBOLS)})",
    )
    parser.add_argument(
        "--days", type=int, default=3,
        help="Number of days of history to fetch (default: 3)",
    )
    args = parser.parse_args()

    # Check credentials
    client = CoinbaseClient()
    if not client.is_configured():
        print("Coinbase is not configured. Check your credentials:")
        print("  COINBASE_KEY_FILE=<path to CDP key JSON>")
        print("  — or —")
        print("  COINBASE_API_KEY=<key>")
        print("  COINBASE_API_SECRET=<secret>")
        return

    print("Coinbase credentials found.")

    # Verify REST client can be created
    try:
        rest = client._get_client()
        print(f"REST client initialized: {type(rest).__name__}")
    except Exception as e:
        print(f"Failed to create REST client: {e}")
        return

    # Fetch prices
    provider = CoinbaseMarketDataProvider(client)
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=args.days - 1)

    symbols = [s.upper() for s in args.symbols]
    print(f"\nFetching {args.days} day(s) of prices for: {', '.join(symbols)}")
    print(f"Date range: {start_date} to {end_date}")
    print()

    try:
        results = provider.get_price_history(symbols, start_date, end_date)
    except Exception as e:
        print(f"Error fetching prices: {e}")
        return

    # Display results
    for symbol in symbols:
        prices = results.get(symbol, [])
        if not prices:
            print(f"  {symbol}: no data returned")
            continue

        print(f"  {symbol}:")
        for pr in prices:
            print(f"    {pr.price_date}  ${pr.close_price:>12,.2f}  (source: {pr.source})")

    # Summary
    print()
    total = sum(len(v) for v in results.values())
    empty = [s for s in symbols if not results.get(s)]
    print(f"Total: {total} price points across {len(symbols)} symbols")
    if empty:
        print(f"No data for: {', '.join(empty)}")


if __name__ == "__main__":
    main()
