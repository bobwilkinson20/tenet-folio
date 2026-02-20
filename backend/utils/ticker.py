"""Utility functions for handling ticker symbols.

Mirrors frontend/src/utils/ticker.ts for consistent behavior.
"""

ZERO_BALANCE_TICKER = "_ZERO_BALANCE"


def is_synthetic_ticker(ticker: str) -> bool:
    """Check if ticker is a synthetic internal identifier.

    Synthetic tickers include:
    - _SF:{hash}      — SimpleFIN provider for non-tradable holdings
    - _MAN:{hash}     — Manual holdings for "Other" assets
    - _ZERO_BALANCE   — Sentinel for accounts with zero holdings

    These should generally be hidden from users in display contexts.
    """
    return (
        ticker.startswith("_SF:")
        or ticker.startswith("_MAN:")
        or ticker == ZERO_BALANCE_TICKER
    )


def is_cash_ticker(ticker: str) -> bool:
    """Check if ticker represents a cash position.

    Cash tickers use the format _CASH:{currency_code}.
    """
    return ticker.startswith("_CASH:")
