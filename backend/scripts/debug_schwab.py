#!/usr/bin/env python3
"""Debug script to inspect raw Charles Schwab API response structures.

Usage:
    cd backend
    uv run python -m scripts.debug_schwab
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from schwab.client import Client

from integrations.schwab_client import SchwabClient


def dump_value(val, indent=6):
    """Pretty-print a value, truncating long strings."""
    if isinstance(val, (dict, list)):
        text = json.dumps(val, default=str, indent=indent)
        if len(text) > 500:
            text = text[:500] + "\n      ..."
        return text
    text = repr(val)
    if len(text) > 200:
        text = text[:200] + "..."
    return text


def inspect_dict(data, prefix="  "):
    """Recursively inspect a dict, showing keys and types."""
    if not isinstance(data, dict):
        print(f"{prefix}(not a dict: {type(data).__name__})")
        return

    for key in data:
        val = data[key]
        if isinstance(val, dict):
            print(f"{prefix}{key}: dict with {len(val)} keys: {list(val.keys())}")
        elif isinstance(val, list):
            print(f"{prefix}{key}: list with {len(val)} items")
            if val:
                first = val[0]
                if isinstance(first, dict):
                    print(f"{prefix}  first item keys: {list(first.keys())}")
                else:
                    print(f"{prefix}  first item: {dump_value(first)}")
        elif isinstance(val, (str, int, float, bool, type(None))):
            print(f"{prefix}{key}: {dump_value(val)}")
        else:
            print(f"{prefix}{key}: {type(val).__name__}")


def main():
    client = SchwabClient()

    if not client.is_configured():
        print("Schwab is not configured. Check .env credentials and token file.")
        print()
        print("Required settings:")
        print("  SCHWAB_APP_KEY=<your app key>")
        print("  SCHWAB_APP_SECRET=<your app secret>")
        print("  SCHWAB_TOKEN_PATH=<path to .schwab_token.json>")
        return

    schwab = client._get_client()

    # --- Account Numbers ---
    print("=== Account Numbers (hash mapping) ===")
    resp = schwab.get_account_numbers()
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        acct_numbers = resp.json()
        print(f"  Response type: {type(acct_numbers).__name__}")
        print(f"  Count: {len(acct_numbers)}")
        for entry in acct_numbers:
            print(f"  Entry keys: {list(entry.keys())}")
            print(f"    accountNumber: {entry.get('accountNumber', '?')}")
            print(f"    hashValue: {entry.get('hashValue', '?')[:12]}...")
    else:
        print(f"  Error: {resp.text[:200]}")
    print()

    # --- Accounts with Positions ---
    print("=== Accounts (with positions) ===")
    resp = schwab.get_accounts(fields=Client.Account.Fields.POSITIONS)
    print(f"  Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  Error: {resp.text[:200]}")
        return

    accounts_data = resp.json()
    print(f"  Response type: {type(accounts_data).__name__}")
    print(f"  Count: {len(accounts_data)}")
    print()

    for i, acct_data in enumerate(accounts_data):
        acct_hash = acct_data.get("hashValue", "?")
        print(f"--- Account {i + 1} (hash: {acct_hash[:12]}...) ---")
        print(f"  Top-level keys: {list(acct_data.keys())}")

        sec_acct = acct_data.get("securitiesAccount", {})
        if sec_acct:
            print(f"  securitiesAccount keys: {list(sec_acct.keys())}")
            print(f"    type: {sec_acct.get('type', '?')}")
            print(f"    accountNumber: {sec_acct.get('accountNumber', '?')}")

            # Positions
            positions = sec_acct.get("positions", []) or []
            print(f"    positions: {len(positions)} items")
            for j, pos in enumerate(positions[:3]):  # Show first 3
                print(f"      Position {j + 1} keys: {list(pos.keys())}")
                instrument = pos.get("instrument", {})
                print(f"        instrument: {instrument}")
                print(f"        longQuantity: {pos.get('longQuantity')}")
                print(f"        shortQuantity: {pos.get('shortQuantity')}")
                print(f"        marketValue: {pos.get('marketValue')}")
            if len(positions) > 3:
                print(f"      ... and {len(positions) - 3} more positions")

            # Balances
            for balance_key in ("currentBalances", "initialBalances", "projectedBalances"):
                balances = sec_acct.get(balance_key, {})
                if balances:
                    print(f"    {balance_key} keys: {list(balances.keys())}")
                    if balance_key == "currentBalances":
                        print(f"      cashBalance: {balances.get('cashBalance')}")
                        print(f"      liquidationValue: {balances.get('liquidationValue')}")
        print()

    # --- Transactions ---
    if not acct_numbers:
        print("No accounts found, skipping transactions.")
        return

    first_hash = acct_numbers[0].get("hashValue", "")
    if not first_hash:
        print("No valid account hash, skipping transactions.")
        return

    print(f"=== Transactions (account: {first_hash[:12]}..., last 60 days) ===")
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=60)

    resp = schwab.get_transactions(
        first_hash,
        start_date=start_date,
        end_date=end_date,
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  Error: {resp.text[:200]}")
        return

    transactions = resp.json()
    print(f"  Response type: {type(transactions).__name__}")
    print(f"  Count: {len(transactions)}")
    print()

    # Show first few transactions
    for i, txn in enumerate(transactions[:5]):
        print(f"--- Transaction {i + 1} ---")
        print(f"  Top-level keys: {list(txn.keys())}")
        print(f"  type: {txn.get('type')}")
        print(f"  transactionSubType: {txn.get('transactionSubType')}")
        print(f"  transactionId: {txn.get('transactionId')}")
        print(f"  activityId: {txn.get('activityId')}")
        print(f"  transactionDate: {txn.get('transactionDate')}")
        print(f"  tradeDate: {txn.get('tradeDate')}")
        print(f"  settlementDate: {txn.get('settlementDate')}")
        print(f"  netAmount: {txn.get('netAmount')}")
        print(f"  description: {txn.get('description')}")
        print(f"  status: {txn.get('status')}")

        transfer_items = txn.get("transferItems", []) or []
        print(f"  transferItems: {len(transfer_items)} items")
        for j, item in enumerate(transfer_items):
            instrument = item.get("instrument", {})
            asset_type = instrument.get("assetType", "?")
            symbol = instrument.get("symbol", "?")
            desc = instrument.get("description", "")
            print(
                f"    Item {j + 1}: {asset_type} {symbol}"
                f" | amount={item.get('amount')}"
                f" | price={item.get('price')}"
                f" | cost={item.get('cost')}"
                f" | feeType={item.get('feeType', '')}"
                f" | desc={desc}"
            )

        fees = txn.get("fees", {})
        if fees:
            print(f"  fees: {fees}")
        print()

    if len(transactions) > 5:
        print(f"... and {len(transactions) - 5} more transactions")

    # Show a summary of transaction types
    print()
    print("=== Transaction Type Summary ===")
    type_counts: dict[str, int] = {}
    for txn in transactions:
        t = txn.get("type", "UNKNOWN")
        sub = txn.get("transactionSubType", "")
        key = f"{t}/{sub}" if sub else t
        type_counts[key] = type_counts.get(key, 0) + 1

    for key, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {key}: {count}")


if __name__ == "__main__":
    main()
