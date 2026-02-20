#!/usr/bin/env python3
"""Coinbase API diagnostic script.

Dumps raw API responses for currency accounts, portfolio breakdown,
and trade fills to help debug holdings and activity sync issues.

Usage:
    cd backend
    uv run python -m scripts.diagnose_coinbase
"""

import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings  # noqa: E402
from coinbase.rest import RESTClient  # noqa: E402
from integrations.coinbase_client import FIAT_CURRENCIES  # noqa: E402


def make_client() -> RESTClient:
    """Create a RESTClient from settings."""
    api_key = settings.COINBASE_API_KEY
    api_secret = settings.COINBASE_API_SECRET
    key_file = settings.COINBASE_KEY_FILE

    if key_file and not (api_key and api_secret):
        path = Path(key_file).expanduser().resolve()
        with open(path) as f:
            data = json.load(f)
        api_key = data.get("name") or data.get("id") or ""
        api_secret = data.get("privateKey") or ""

    if not api_key or not api_secret:
        print("ERROR: Coinbase credentials not configured in .env")
        sys.exit(1)

    return RESTClient(api_key=api_key, api_secret=api_secret)


def to_decimal(value) -> Decimal:
    """Safely convert to Decimal."""
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def get_field(obj, field):
    """Extract field from dict or object."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def get_nested_decimal(obj, outer, inner) -> Decimal:
    """Extract nested decimal like obj.outer.inner."""
    outer_obj = get_field(obj, outer)
    if outer_obj is None:
        return Decimal("0")
    raw = get_field(outer_obj, inner)
    if raw is None:
        return Decimal("0")
    return to_decimal(raw)


def dump_obj(obj, label=""):
    """Pretty-print an API response object."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return {k: repr(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {"_raw": repr(obj)}


def main():
    client = make_client()

    # ── Portfolios ──────────────────────────────────────────────
    print("=" * 70)
    print("PORTFOLIOS")
    print("=" * 70)
    portfolios_resp = client.get_portfolios()
    portfolios = get_field(portfolios_resp, "portfolios") or []
    if not portfolios:
        print("  (none)")
        return

    for p in portfolios:
        pid = get_field(p, "uuid") or get_field(p, "id") or "?"
        name = get_field(p, "name") or "?"
        print(f"  {name}  (uuid={pid})")
    print()

    # ── Currency accounts per portfolio ─────────────────────────
    for p in portfolios:
        pid = get_field(p, "uuid") or get_field(p, "id") or ""
        pname = get_field(p, "name") or "?"
        print("=" * 70)
        print(f"CURRENCY ACCOUNTS — {pname} ({pid})")
        print("=" * 70)

        all_accounts = []
        cursor = None
        page = 0
        while True:
            kwargs = {"limit": 250, "retail_portfolio_id": pid}
            if cursor:
                kwargs["cursor"] = cursor
            resp = client.get_accounts(**kwargs)
            accounts = get_field(resp, "accounts") or []
            all_accounts.extend(accounts)
            page += 1

            next_cursor = get_field(resp, "cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        print(f"  Total currency accounts returned: {len(all_accounts)} (pages: {page})")
        print()

        # Separate into non-zero and zero-balance
        non_zero = []
        zero_but_notable = []

        for acct in all_accounts:
            currency = get_field(acct, "currency") or "?"
            active = get_field(acct, "active")
            available = get_nested_decimal(acct, "available_balance", "value")
            hold = get_nested_decimal(acct, "hold", "value")
            total = available + hold

            entry = {
                "currency": currency,
                "active": active,
                "available_balance": available,
                "hold": hold,
                "total": total,
            }

            if total != Decimal("0"):
                non_zero.append((entry, acct))
            elif currency in ("SOL", "ETC", "BTC", "SUI", "ETH"):
                # Show these even if zero so we can see the raw data
                zero_but_notable.append((entry, acct))

        # Print non-zero holdings
        print(f"  Non-zero balances: {len(non_zero)}")
        print("-" * 70)
        for entry, acct in sorted(non_zero, key=lambda x: x[0]["currency"]):
            currency = entry["currency"]
            is_fiat = currency.upper() in FIAT_CURRENCIES
            would_map_to = f"_CASH:{currency.upper()}" if is_fiat else currency.upper()
            active_str = "active" if entry["active"] else "INACTIVE"
            filter_reason = ""
            if entry["active"] is not None and not entry["active"]:
                filter_reason = " *** WOULD BE FILTERED (inactive) ***"

            print(f"  {currency:>8s}  available={str(entry['available_balance']):>20s}"
                  f"  hold={str(entry['hold']):>15s}"
                  f"  total={str(entry['total']):>20s}"
                  f"  {active_str}{filter_reason}")
            print(f"           -> maps to symbol={would_map_to}")

            # Try price lookup for crypto
            if not is_fiat:
                try:
                    product_resp = client.get_product(f"{currency.upper()}-USD")
                    price_str = get_field(product_resp, "price")
                    price = to_decimal(price_str)
                    mv = entry["total"] * price
                    print(f"           -> price={price}  market_value={mv}")
                except Exception as e:
                    print(f"           -> price lookup {currency}-USD FAILED: {e}")
                    try:
                        product_resp = client.get_product(f"{currency.upper()}-USDT")
                        price_str = get_field(product_resp, "price")
                        price = to_decimal(price_str)
                        mv = entry["total"] * price
                        print(f"           -> fallback {currency}-USDT price={price}  market_value={mv}")
                    except Exception as e2:
                        print(f"           -> fallback {currency}-USDT ALSO FAILED: {e2}")

            # Dump all raw fields
            raw = dump_obj(acct)
            print(f"           RAW: {json.dumps(raw, indent=None, default=str)}")
            print()

        # Print notable zero-balance currencies
        if zero_but_notable:
            print()
            print("  Zero-balance (notable currencies only):")
            print("-" * 70)
            for entry, acct in zero_but_notable:
                currency = entry["currency"]
                active_str = "active" if entry["active"] else "INACTIVE"
                raw = dump_obj(acct)
                print(f"  {currency:>8s}  available={str(entry['available_balance']):>20s}"
                      f"  hold={str(entry['hold']):>15s}"
                      f"  total={str(entry['total']):>20s}"
                      f"  {active_str}")
                print(f"           RAW: {json.dumps(raw, indent=None, default=str)}")
                print()

        print()

    # ── Portfolio breakdown (alternative data source) ───────────
    print("=" * 70)
    print("PORTFOLIO BREAKDOWN (alternative endpoint)")
    print("=" * 70)
    print("This shows how Coinbase itself values each position.\n")

    for p in portfolios:
        pid = get_field(p, "uuid") or get_field(p, "id") or ""
        pname = get_field(p, "name") or "?"
        print(f"  Portfolio: {pname} ({pid})")
        try:
            breakdown = client.get_portfolio_breakdown(pid)
            # Look for spot positions
            bd = get_field(breakdown, "breakdown")
            if bd is None:
                bd = breakdown

            spot_positions = get_field(bd, "spot_positions") or []
            print(f"  spot_positions count: {len(spot_positions)}")

            for pos in spot_positions:
                asset = get_field(pos, "asset") or get_field(pos, "symbol") or "?"
                total_balance = get_field(pos, "total_balance_crypto") or get_field(pos, "account_balance_crypto") or "?"
                total_fiat = get_field(pos, "total_balance_fiat") or get_field(pos, "account_balance_fiat") or "?"

                print(f"    {asset:>8s}  crypto_balance={total_balance}"
                      f"  fiat_value={total_fiat}")

                # Dump raw
                raw = dump_obj(pos)
                print(f"             RAW: {json.dumps(raw, indent=None, default=str)}")
                print()

        except Exception as e:
            print(f"  ERROR: {e}")
        print()

    # ── Trade fills (activities) ──────────────────────────────
    dump_fills(client, portfolios)

    # ── V2 transactions (deposits, receives, staking, etc.) ──
    # Uses get_accounts() UUIDs to hit v2 transactions endpoint
    dump_v2_transactions(client, portfolios)


def dump_fills(client, portfolios):
    """Dump trade fills (activities) from the API."""
    print("=" * 70)
    print("TRADE FILLS (activities)")
    print("=" * 70)

    # ── Global fills (no portfolio filter) ─────────────────────
    print("\n  --- All fills (no portfolio filter) ---")
    all_fills = paginate_fills(client)
    print(f"  Total fills returned: {len(all_fills)}")
    print_fills(all_fills)

    # ── Per-portfolio fills ────────────────────────────────────
    for p in portfolios:
        pid = get_field(p, "uuid") or get_field(p, "id") or ""
        pname = get_field(p, "name") or "?"
        print(f"\n  --- Fills for portfolio: {pname} ({pid}) ---")
        try:
            fills = paginate_fills(client, portfolio_id=pid)
            print(f"  Fills returned: {len(fills)}")
            print_fills(fills)
        except Exception as e:
            print(f"  ERROR: {e}")

    print()


def paginate_fills(client, portfolio_id=None):
    """Paginate through get_fills(), return all fill objects."""
    all_fills = []
    cursor = None
    while True:
        kwargs = {"limit": 100}
        if portfolio_id:
            kwargs["retail_portfolio_id"] = portfolio_id
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.get_fills(**kwargs)
        fills = get_field(resp, "fills") or []
        all_fills.extend(fills)
        next_cursor = get_field(resp, "cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    return all_fills


def print_fills(fills):
    """Print a summary table of fills."""
    if not fills:
        print("  (none)")
        return

    print("-" * 70)
    for fill in fills:
        entry_id = get_field(fill, "entry_id") or get_field(fill, "trade_id") or "?"
        product_id = get_field(fill, "product_id") or "?"
        side = get_field(fill, "side") or "?"
        price = get_field(fill, "price") or "?"
        size = get_field(fill, "size") or "?"
        commission = get_field(fill, "commission") or "0"
        trade_time = get_field(fill, "trade_time") or "?"
        retail_portfolio_id = get_field(fill, "retail_portfolio_id") or ""

        print(f"  {trade_time}  {side:>4s}  {product_id:<10s}"
              f"  size={size}  price={price}"
              f"  commission={commission}  id={entry_id}")
        if retail_portfolio_id:
            print(f"    retail_portfolio_id={retail_portfolio_id}")

        raw = dump_obj(fill)
        print(f"    RAW: {json.dumps(raw, indent=None, default=str)}")
        print()


def dump_v2_transactions(client, portfolios):
    """Dump v2 transactions using get_accounts() UUIDs.

    The v2 /v2/accounts/:id/transactions endpoint accepts the same UUIDs
    returned by the v3 get_accounts() call. Using v3 UUIDs avoids the 401
    errors that occur when using v2-specific account IDs with CDP keys.
    """
    print("=" * 70)
    print("V2 TRANSACTIONS (transfers, deposits, receives, staking, etc.)")
    print("=" * 70)
    print("Uses get_accounts() UUIDs to fetch v2 transaction history.\n")

    # Get currency accounts via v3 get_accounts() — same call gem_coinbase.py uses
    all_currency_accounts = []
    cursor = None
    while True:
        kwargs = {"limit": 250}
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.get_accounts(**kwargs)
        accounts = get_field(resp, "accounts") or []
        all_currency_accounts.extend(accounts)
        next_cursor = get_field(resp, "cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    print(f"  Currency accounts from get_accounts(): {len(all_currency_accounts)}")

    type_counts: dict[str, int] = {}
    total_txns = 0

    for acct in all_currency_accounts:
        acct_uuid = get_field(acct, "uuid") or get_field(acct, "id") or ""
        currency = get_field(acct, "currency") or "?"
        acct_name = get_field(acct, "name") or currency

        # Paginate v2 transactions for this account
        # NOTE: query params must NOT be embedded in the URL path —
        # the SDK signs the path for JWT auth and inline params cause 401s.
        txns = []
        endpoint = f"/v2/accounts/{acct_uuid}/transactions"
        starting_after = None
        while True:
            try:
                if starting_after:
                    txn_resp = client.get(endpoint, params={"starting_after": starting_after})
                else:
                    txn_resp = client.get(endpoint)
            except Exception as e:
                print(f"  ERROR fetching transactions for {acct_name}: {e}")
                break

            page_data = get_field(txn_resp, "data") or []
            txns.extend(page_data)

            if not page_data:
                break

            pagination = get_field(txn_resp, "pagination")
            starting_after = get_field(pagination, "next_starting_after") if pagination else None
            if not starting_after:
                break

        if not txns:
            continue

        total_txns += len(txns)
        print(f"\n  --- {acct_name} ({currency}) — uuid={acct_uuid}"
              f" — {len(txns)} transactions ---")
        print("-" * 70)

        for txn in txns:
            txn_id = get_field(txn, "id") or "?"
            txn_type = get_field(txn, "type") or "?"
            status = get_field(txn, "status") or "?"
            created_at = get_field(txn, "created_at") or "?"

            amount_obj = get_field(txn, "amount") or {}
            amount = get_field(amount_obj, "amount") or "?"
            amount_currency = get_field(amount_obj, "currency") or "?"

            native_obj = get_field(txn, "native_amount") or {}
            native_amount = get_field(native_obj, "amount") or "?"
            native_currency = get_field(native_obj, "currency") or "?"

            description = get_field(txn, "description") or ""

            type_counts[txn_type] = type_counts.get(txn_type, 0) + 1

            print(f"  {created_at}  {txn_type:<25s}  {status:<10s}"
                  f"  {amount} {amount_currency}"
                  f"  (native: {native_amount} {native_currency})"
                  f"  id={txn_id}")
            if description:
                print(f"    description: {description}")

            network = get_field(txn, "network")
            if network:
                net_status = get_field(network, "status") or ""
                tx_hash = get_field(network, "hash") or ""
                if net_status or tx_hash:
                    print(f"    network: status={net_status}  hash={tx_hash}")

            raw = dump_obj(txn)
            print(f"    RAW: {json.dumps(raw, indent=None, default=str)}")
            print()

    print()
    print(f"  Total v2 transactions across all accounts: {total_txns}")
    if type_counts:
        print("  Transaction type summary:")
        for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {t:<30s} {count}")
    print()


if __name__ == "__main__":
    main()
