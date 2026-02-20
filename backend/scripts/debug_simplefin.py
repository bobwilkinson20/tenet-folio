#!/usr/bin/env python3
"""Debug script to inspect raw SimpleFIN API response data.

Shows per-account balance vs holdings total to diagnose cash derivation issues.

Usage:
    cd backend
    uv run python -m scripts.debug_simplefin
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.simplefin_client import SimpleFINClient


def main():
    client = SimpleFINClient()

    if not client.is_configured():
        print("SimpleFIN is not configured. Check .env for SIMPLEFIN_ACCESS_URL.")
        return

    print("Fetching SimpleFIN data...\n")
    data = client._fetch_data()

    errors = data.get("errors", [])
    if errors:
        print(f"Provider errors: {errors}\n")

    accounts = data.get("accounts", [])
    print(f"Total accounts: {len(accounts)}\n")

    for acc in accounts:
        acct_id = acc.get("id", "?")
        name = acc.get("name", "?")
        org = acc.get("org", {})
        institution = org.get("name", "Unknown") if org else "Unknown"
        balance_raw = acc.get("balance")
        currency = acc.get("currency", "USD") or "USD"
        balance_date = acc.get("balance-date")

        print(f"=== {name} ({institution}) ===")
        print(f"  ID: {acct_id}")
        print(f"  Currency: {currency!r}")
        print(f"  Balance (raw): {balance_raw!r}")
        print(f"  Balance-date: {balance_date}")

        # Parse balance
        balance = None
        if balance_raw is not None:
            try:
                balance = Decimal(str(balance_raw))
            except Exception:
                print(f"  *** Could not parse balance: {balance_raw!r}")

        # Process holdings
        raw_holdings = acc.get("holdings") or []
        print(f"  Holdings: {len(raw_holdings)}")

        holdings_total = Decimal("0")
        for h in raw_holdings:
            symbol = h.get("symbol") or "(no symbol)"
            shares = h.get("shares", "0")
            mv_raw = h.get("market_value", "0")
            desc = h.get("description", "")
            h_currency = h.get("currency", "")

            try:
                mv = Decimal(str(mv_raw)) if mv_raw else Decimal("0")
            except Exception:
                mv = Decimal("0")

            holdings_total += mv
            print(f"    {symbol:20s}  shares={shares:>12s}  mv={str(mv):>14s}  cur={h_currency:4s}  {desc}")

        print(f"  Holdings total: {holdings_total}")

        if balance is not None:
            cash = balance - holdings_total
            print(f"  Derived cash:   {cash}")
            if cash == 0:
                print("  -> No cash holding (balance == holdings)")
            elif cash > 0:
                print(f"  -> Would create _CASH:{currency} = {cash}")
            else:
                print(f"  -> Would create NEGATIVE _CASH:{currency} = {cash}")
        else:
            print("  -> No cash (balance field missing)")

        print()


if __name__ == "__main__":
    main()
