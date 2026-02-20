"""Debug script to inspect raw SnapTrade activity/transaction response structure.

This is a temporary utility to understand the shape of activity data from
SnapTrade's get_activities endpoint, to help design the normalized Activity model.

Usage:
    cd backend
    uv run python -m scripts.debug_snaptrade_activities
    uv run python -m scripts.debug_snaptrade_activities --days 90
    uv run python -m scripts.debug_snaptrade_activities --start 2025-01-01 --end 2025-06-01
"""

import argparse
import json
from datetime import date, timedelta

from integrations.snaptrade_client import SnapTradeClient


def serialize(obj):
    """Best-effort serializer for SnapTrade SDK objects."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (date,)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serialize(item) for item in obj]
    # SDK objects often behave like dicts
    if hasattr(obj, "items"):
        try:
            return {k: serialize(v) for k, v in obj.items()}
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return {k: serialize(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)


def main():
    parser = argparse.ArgumentParser(description="Debug SnapTrade activities")
    parser.add_argument("--days", type=int, default=30, help="Number of days to look back (default: 30)")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD), overrides --days")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--account", type=str, help="Filter to a specific account ID")
    parser.add_argument("--type", type=str, help="Filter by activity type (e.g. BUY, SELL, DIVIDEND)")
    args = parser.parse_args()

    client = SnapTradeClient()

    if not client.is_configured():
        print("SnapTrade is not configured. Check .env credentials.")
        return

    # List accounts first for context
    print("=== SnapTrade Accounts ===")
    accounts = client.get_accounts()
    for acc in accounts:
        print(f"  {acc.id} - {acc.name} ({acc.brokerage_name})")
    print()

    # Build date range
    end_date = date.fromisoformat(args.end) if args.end else date.today()
    if args.start:
        start_date = date.fromisoformat(args.start)
    else:
        start_date = end_date - timedelta(days=args.days)

    print(f"=== Fetching activities from {start_date} to {end_date} ===")
    print()

    # Build kwargs
    kwargs = {
        "user_id": client.user_id,
        "user_secret": client.user_secret,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    if args.account:
        kwargs["accounts"] = args.account
    if args.type:
        kwargs["type"] = args.type

    response = client.client.transactions_and_reporting.get_activities(**kwargs)

    # Unwrap response
    if hasattr(response, "body"):
        data = response.body
    else:
        data = response

    print(f"Response type: {type(data).__name__}")

    if isinstance(data, list):
        activities = data
    elif isinstance(data, dict):
        print(f"Top-level keys: {list(data.keys())}")
        activities = data.get("activities") or data.get("items") or data
        if not isinstance(activities, list):
            activities = [data]
    elif hasattr(data, "__iter__"):
        activities = list(data)
    else:
        print(f"Unexpected response format: {data}")
        return

    print(f"Total activities: {len(activities)}")
    print()

    if not activities:
        print("No activities found in this date range. Try a wider range with --days 90")
        return

    # Show first activity in detail
    first = activities[0]
    print("=== First Activity (full detail) ===")
    print(f"  Python type: {type(first).__name__}")
    print()

    serialized = serialize(first)
    print(json.dumps(serialized, indent=2, default=str))
    print()

    # Show all unique keys across all activities
    all_keys = set()
    for act in activities:
        if isinstance(act, dict):
            all_keys.update(act.keys())
        elif hasattr(act, "items"):
            try:
                all_keys.update(dict(act.items()).keys())
            except Exception:
                pass
        elif hasattr(act, "__dict__"):
            all_keys.update(k for k in vars(act) if not k.startswith("_"))

    if all_keys:
        print(f"=== All keys across {len(activities)} activities ===")
        for key in sorted(all_keys):
            print(f"  {key}")
        print()

    # Summarize activity types
    type_counts = {}
    for act in activities:
        if isinstance(act, dict):
            act_type = act.get("type", "UNKNOWN")
        elif hasattr(act, "get"):
            act_type = act.get("type", "UNKNOWN")
        else:
            act_type = getattr(act, "type", "UNKNOWN")
        type_counts[str(act_type)] = type_counts.get(str(act_type), 0) + 1

    print("=== Activity Type Summary ===")
    for act_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {act_type}: {count}")
    print()

    # Show a few sample activities with key fields
    print("=== Sample Activities (up to 10) ===")
    for i, act in enumerate(activities[:10]):
        s = serialize(act)
        act_id = s.get("id", "?")
        act_type = s.get("type", "?")
        description = s.get("description", "?")
        trade_date = s.get("trade_date", s.get("settlement_date", "?"))
        amount = s.get("amount", "?")
        price = s.get("price", "?")
        units = s.get("units", "?")
        fee = s.get("fee", "?")
        symbol = s.get("symbol")
        if isinstance(symbol, dict):
            symbol = symbol.get("symbol", symbol.get("description", "?"))

        print(f"  [{i+1}] {act_type} | {trade_date} | {symbol} | "
              f"units={units} price={price} amount={amount} fee={fee}")
        print(f"       desc: {description}")
        print(f"       id: {act_id}")

        # Show account info
        account = s.get("account")
        if isinstance(account, dict):
            print(f"       account: {account.get('name', '?')} ({account.get('id', '?')[:8]}...)")
        print()

    # Dump all activities as JSON for offline analysis
    print("=== Full JSON dump (all activities) ===")
    all_serialized = [serialize(act) for act in activities]
    print(json.dumps(all_serialized, indent=2, default=str))


if __name__ == "__main__":
    main()
