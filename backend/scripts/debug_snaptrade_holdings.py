"""Debug script to inspect raw SnapTrade holdings response structure.

Usage:
    cd backend
    uv run python -m scripts.debug_snaptrade_holdings
"""

import json
from integrations.snaptrade_client import SnapTradeClient


def main():
    client = SnapTradeClient()

    if not client.is_configured():
        print("SnapTrade is not configured. Check .env credentials.")
        return

    print("=== SnapTrade Accounts ===")
    accounts = client.get_accounts()
    for acc in accounts:
        print(f"  {acc.id} - {acc.name} ({acc.brokerage_name})")

    print()

    for acc in accounts:
        print(f"=== Raw holdings response for {acc.name} ({acc.id}) ===")
        response = client.client.account_information.get_user_holdings(
            account_id=acc.id,
            user_id=client.user_id,
            user_secret=client.user_secret,
        )

        # Show the raw type
        print(f"  Response type: {type(response).__name__}")

        # Try to get the underlying data
        if hasattr(response, "body"):
            data = response.body
            print(f"  .body type: {type(data).__name__}")
        else:
            data = response
            print("  (no .body attribute, using response directly)")

        # Dump top-level keys
        if isinstance(data, dict):
            print(f"  Top-level keys: {list(data.keys())}")
            for key in data:
                val = data[key]
                if isinstance(val, (dict, str, bool, int, float, type(None))):
                    print(f"    {key}: {json.dumps(val, default=str, indent=6)}")
                elif isinstance(val, list):
                    print(f"    {key}: list with {len(val)} items")
                    if val:
                        print(f"      first item type: {type(val[0]).__name__}")
                        if isinstance(val[0], dict):
                            print(f"      first item keys: {list(val[0].keys())}")
                else:
                    print(f"    {key}: {type(val).__name__}")
                    if hasattr(val, "__dict__"):
                        for attr, attr_val in vars(val).items():
                            if not attr.startswith("_"):
                                print(f"      .{attr} = {attr_val!r}")
        elif isinstance(data, list):
            print(f"  Response is a list with {len(data)} items")
            if data:
                first = data[0]
                print(f"  First item type: {type(first).__name__}")
                if isinstance(first, dict):
                    print(f"  First item keys: {list(first.keys())}")
        elif hasattr(data, "__dict__"):
            print("  Attributes:")
            for attr in sorted(dir(data)):
                if not attr.startswith("_"):
                    try:
                        val = getattr(data, attr)
                        if not callable(val):
                            val_repr = repr(val)
                            if len(val_repr) > 200:
                                val_repr = val_repr[:200] + "..."
                            print(f"    .{attr} = {val_repr}")
                    except Exception:
                        pass

        print()


if __name__ == "__main__":
    main()
