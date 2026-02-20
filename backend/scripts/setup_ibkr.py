#!/usr/bin/env python3
"""Interactive Brokers Flex Web Service setup script.

This script validates IBKR Flex credentials by attempting a test download.

Usage:
    1. Log in to IBKR Client Portal / Account Management
    2. Go to Settings > Flex Web Service Configuration to generate a token
    3. Create a Flex Query under Reports > Flex Queries > Custom Flex Queries
    4. Run this script and enter your token and query ID when prompted
    5. Add the resulting env vars to your .env file
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ibflex import client, parser


def _offer_keychain_store(credentials: dict[str, str]) -> None:
    """Prompt the user to store credentials in macOS Keychain."""
    try:
        from services.credential_manager import set_credential
    except ImportError:
        return

    answer = input("\nStore these credentials in macOS Keychain? [Y/n] ").strip().lower()
    if answer in ("", "y", "yes"):
        for key, value in credentials.items():
            if set_credential(key, value):
                print(f"  Stored {key} in keychain")
            else:
                print(f"  Failed to store {key}")
    else:
        print("  Skipped keychain storage.")


def validate_credentials(token: str, query_id: str) -> bytes:
    """Validate IBKR Flex credentials by attempting a download.

    Args:
        token: Flex Web Service token.
        query_id: Flex Query ID.

    Returns:
        Raw XML bytes from the Flex report.

    Raises:
        ibflex.client.IbflexClientError: If credentials are invalid.
    """
    return client.download(token, query_id)


def validate_query_sections(data: bytes) -> list[str]:
    """Parse a Flex report and return a list of missing required sections.

    Args:
        data: Raw XML bytes from a Flex report download.

    Returns:
        List of section names that are missing from the query.
        Empty list means all required sections are present.
    """
    response = parser.parse(data)
    missing = []
    for stmt in response.FlexStatements:
        if not stmt.OpenPositions and "Open Positions" not in missing:
            missing.append("Open Positions")
        if not stmt.CashReport and "Cash Report" not in missing:
            missing.append("Cash Report")
        if not stmt.Trades and "Trades" not in missing:
            missing.append("Trades")
    return missing


# Trades columns required for activity sync (ibflex Trade field names)
REQUIRED_TRADE_COLUMNS = {"tradeID", "tradeDate"}
RECOMMENDED_TRADE_COLUMNS = {"buySell", "netCash", "ibCommission", "settleDateTarget"}


def validate_trade_columns(data: bytes) -> tuple[list[str], list[str]]:
    """Check that the Trades section has the columns needed for activity sync.

    Args:
        data: Raw XML bytes from a Flex report download.

    Returns:
        Tuple of (missing_required, missing_recommended) column name lists.
    """
    response = parser.parse(data)
    missing_required = []
    missing_recommended = []

    for stmt in response.FlexStatements:
        if not stmt.Trades:
            # No trades to inspect — can't validate columns
            return list(REQUIRED_TRADE_COLUMNS), list(RECOMMENDED_TRADE_COLUMNS)

        # Inspect the first trade to see which fields are populated
        trade = stmt.Trades[0]
        for col in REQUIRED_TRADE_COLUMNS:
            val = getattr(trade, col, None)
            if val is None and col not in missing_required:
                missing_required.append(col)
        for col in RECOMMENDED_TRADE_COLUMNS:
            val = getattr(trade, col, None)
            if val is None and col not in missing_recommended:
                missing_recommended.append(col)
        break  # Only need to check one statement

    return missing_required, missing_recommended


def main():
    """Prompt for credentials and validate them."""
    print("Interactive Brokers Flex Web Service Setup")
    print("=" * 50)
    print()
    print("This script will validate your IBKR Flex credentials.")
    print()
    print("To get your Flex Token:")
    print("  1. Log in to IBKR Client Portal / Account Management")
    print("  2. Go to Settings > Flex Web Service Configuration")
    print("  3. Generate a token (or use your existing one)")
    print()
    print("To create a Flex Query:")
    print("  1. Go to Reports > Flex Queries > Custom Flex Queries")
    print("  2. Click 'Configure' to create a new Activity Flex Query")
    print("  3. Include these sections: Open Positions, Cash Report, Trades")
    print("     For the Trades section, include at minimum these columns:")
    print("       TradeID, TradeDate, Buy/Sell, NetCash, IBCommission,")
    print("       SettleDateTarget")
    print("  4. Recommended settings:")
    print("     - Period: Last 365 Calendar Days")
    print("     - Date format: yyyy-MM-dd")
    print("     - Time format: HH:mm:ss")
    print("     - Format: XML")
    print("  5. Note the Query ID shown on the Flex Queries page")
    print()

    token = input("Enter your Flex Token: ").strip()

    if not token:
        print("Error: No token provided")
        sys.exit(1)

    query_id = input("Enter your Flex Query ID: ").strip()

    if not query_id:
        print("Error: No query ID provided")
        sys.exit(1)

    print()
    print("Validating credentials...")

    try:
        data = validate_credentials(token, query_id)

        # Check for required query sections
        missing = validate_query_sections(data)

        # Check for required query sections
        print()
        print("Checking Flex Query sections...")
        if missing:
            print()
            print("Warning: Your Flex Query is missing these sections:")
            for section in missing:
                print(f"  - {section}")
            print()
            print("To add missing sections:")
            print("  1. Go to Reports > Flex Queries > Custom Flex Queries")
            print("  2. Click 'Configure' on your query")
            print("  3. Add the missing sections listed above")
        else:
            print("  Open Positions: found")
            print("  Cash Report:    found")
            print("  Trades:         found")

        # Validate Trades columns for activity sync
        missing_req, missing_rec = validate_trade_columns(data)
        if missing_req or missing_rec:
            print()
            print("Checking Trades columns for activity sync...")
            if missing_req:
                print()
                print("  WARNING: Missing required Trades columns (activities will")
                print("  NOT sync without these):")
                for col in missing_req:
                    print(f"    - {col}")
            if missing_rec:
                print()
                print("  Note: Missing recommended Trades columns (activities will")
                print("  sync but with incomplete data):")
                for col in missing_rec:
                    print(f"    - {col}")
            print()
            print("  To add columns: Reports > Flex Queries > Configure your query")
            print("  > Trades section > check the missing columns above.")
        elif not missing:
            # Only show if we had trades to inspect
            print("  Trades columns: all required columns present")

        print()
        print("Success! Add the following to your .env file:")
        print()
        print(f"IBKR_FLEX_TOKEN={token}")
        print(f"IBKR_FLEX_QUERY_ID={query_id}")
        print()
        print("Keep these credentials secure - they provide read-only")
        print("access to your account data via the Flex Web Service.")
        _offer_keychain_store(
            {"IBKR_FLEX_TOKEN": token, "IBKR_FLEX_QUERY_ID": query_id}
        )

    except Exception as e:
        print(f"Error: {e}")
        print()
        print("Common issues:")
        print("  - Token has expired (regenerate in Client Portal)")
        print("  - Token is invalid (check for typos)")
        print("  - Query ID is invalid (check Flex Queries page)")
        print("  - IP restriction (whitelist your IP in Flex settings)")
        print("  - Too many requests (wait and try again)")
        sys.exit(1)


if __name__ == "__main__":
    main()
