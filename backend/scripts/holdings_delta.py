#!/usr/bin/env python
"""Compare holdings between two dates to identify valuation changes.

Shows added/removed holdings, quantity changes, price changes, and value
deltas between any two dates that have DailyHoldingValue records.

Usage:
    cd backend
    uv run python -m scripts.holdings_delta 2026-01-15 2026-01-16
    uv run python -m scripts.holdings_delta 2026-01-15 2026-01-16 --account "Vanguard"
    uv run python -m scripts.holdings_delta 2026-01-15 2026-01-16 --sort value_delta
"""

import argparse
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from database import get_session_local
from models import Account, DailyHoldingValue
from utils.ticker import is_synthetic_ticker


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _fmt_dec(val: Decimal, places: int = 2) -> str:
    """Format decimal with thousands separator."""
    fmt = f",.{places}f"
    return format(float(val), fmt)


def _fmt_delta(val: Decimal, places: int = 2) -> str:
    """Format delta with sign and thousands separator."""
    prefix = "+" if val > 0 else ""
    return f"{prefix}{_fmt_dec(val, places)}"


def _load_dhv(db: Session, target_date: date, account_ids: list[str] | None) -> dict[tuple[str, str], DailyHoldingValue]:
    """Load DHV rows for a date, keyed by (account_id, security_id)."""
    query = (
        db.query(DailyHoldingValue)
        .filter(DailyHoldingValue.valuation_date == target_date)
        .options(
            joinedload(DailyHoldingValue.account),
            joinedload(DailyHoldingValue.security),
        )
    )
    if account_ids:
        query = query.filter(DailyHoldingValue.account_id.in_(account_ids))

    rows = query.all()
    return {(r.account_id, r.security_id): r for r in rows}


def holdings_delta(date_a: date, date_b: date, account_filter: str | None = None, sort_by: str = "value_delta"):
    """Compare holdings between two dates."""
    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        # Resolve account filter
        account_ids = None
        if account_filter:
            accounts = (
                db.query(Account)
                .filter(Account.name.ilike(f"%{account_filter}%"))
                .all()
            )
            if not accounts:
                print(f"No accounts matching '{account_filter}'")
                return
            account_ids = [a.id for a in accounts]
            print(f"Filtering to {len(accounts)} account(s): {', '.join(a.name for a in accounts)}")
            print()

        dhv_a = _load_dhv(db, date_a, account_ids)
        dhv_b = _load_dhv(db, date_b, account_ids)

        if not dhv_a and not dhv_b:
            print(f"No DHV data found for either {date_a} or {date_b}")
            return

        all_keys = set(dhv_a.keys()) | set(dhv_b.keys())

        # Build delta rows
        deltas = []
        for key in all_keys:
            a = dhv_a.get(key)
            b = dhv_b.get(key)

            acct_name = (a or b).account.name
            ticker = (a or b).ticker
            sec_name = (a or b).security.name if (a or b).security else None

            qty_a = a.quantity if a else Decimal("0")
            qty_b = b.quantity if b else Decimal("0")
            price_a = a.close_price if a else Decimal("0")
            price_b = b.close_price if b else Decimal("0")
            val_a = a.market_value if a else Decimal("0")
            val_b = b.market_value if b else Decimal("0")

            qty_delta = qty_b - qty_a
            price_delta = price_b - price_a
            value_delta = val_b - val_a

            if a and not b:
                change_type = "REMOVED"
            elif b and not a:
                change_type = "ADDED"
            elif qty_delta != 0:
                change_type = "QTY CHG"
            elif price_delta != 0:
                change_type = "PRICE"
            else:
                change_type = "—"

            deltas.append({
                "account": acct_name,
                "ticker": ticker,
                "name": sec_name,
                "change_type": change_type,
                "qty_a": qty_a,
                "qty_b": qty_b,
                "qty_delta": qty_delta,
                "price_a": price_a,
                "price_b": price_b,
                "price_delta": price_delta,
                "val_a": val_a,
                "val_b": val_b,
                "value_delta": value_delta,
            })

        # Sort
        if sort_by == "value_delta":
            deltas.sort(key=lambda d: abs(d["value_delta"]), reverse=True)
        elif sort_by == "ticker":
            deltas.sort(key=lambda d: (d["account"], d["ticker"]))
        elif sort_by == "account":
            deltas.sort(key=lambda d: (d["account"], abs(d["value_delta"])), reverse=True)

        # Print summary
        total_a = sum(d["val_a"] for d in deltas)
        total_b = sum(d["val_b"] for d in deltas)
        total_delta = total_b - total_a

        print(f"Holdings delta: {date_a} → {date_b}")
        print(f"{'=' * 80}")
        print(f"Total value {date_a}: ${_fmt_dec(total_a)}")
        print(f"Total value {date_b}: ${_fmt_dec(total_b)}")
        print(f"Delta:                ${_fmt_delta(total_delta)}")
        print()

        # Print by-account summary
        acct_deltas: dict[str, Decimal] = {}
        for d in deltas:
            acct_deltas[d["account"]] = acct_deltas.get(d["account"], Decimal("0")) + d["value_delta"]
        if len(acct_deltas) > 1:
            print("By account:")
            for acct, delta in sorted(acct_deltas.items(), key=lambda x: abs(x[1]), reverse=True):
                print(f"  {acct:<40} ${_fmt_delta(delta)}")
            print()

        # Print detail table - only rows with changes
        changed = [d for d in deltas if d["value_delta"] != 0]
        if not changed:
            print("No value changes between these dates.")
            return

        print(f"{'Type':<9} {'Account':<25} {'Ticker':<10} "
              f"{'Qty Δ':>12} {'Price A':>10} {'Price B':>10} "
              f"{'Value A':>14} {'Value B':>14} {'Value Δ':>14}")
        print(f"{'-' * 9} {'-' * 25} {'-' * 10} "
              f"{'-' * 12} {'-' * 10} {'-' * 10} "
              f"{'-' * 14} {'-' * 14} {'-' * 14}")

        for d in changed:
            ticker_display = d["ticker"]
            if ticker_display and is_synthetic_ticker(ticker_display):
                # Synthetic ticker — show name instead
                ticker_display = (d["name"] or ticker_display)[:10]

            qty_delta_str = _fmt_delta(d["qty_delta"], 4) if d["qty_delta"] != 0 else "—"

            print(
                f"{d['change_type']:<9} "
                f"{d['account'][:25]:<25} "
                f"{ticker_display[:10]:<10} "
                f"{qty_delta_str:>12} "
                f"{_fmt_dec(d['price_a'], 4):>10} "
                f"{_fmt_dec(d['price_b'], 4):>10} "
                f"${_fmt_dec(d['val_a']):>13} "
                f"${_fmt_dec(d['val_b']):>13} "
                f"${_fmt_delta(d['value_delta']):>13}"
            )

        # Show unchanged count
        unchanged = len(deltas) - len(changed)
        if unchanged > 0:
            print(f"\n({unchanged} holdings unchanged)")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Compare holdings between two dates")
    parser.add_argument("date_a", help="First date (YYYY-MM-DD)")
    parser.add_argument("date_b", help="Second date (YYYY-MM-DD)")
    parser.add_argument("--account", "-a", help="Filter by account name (substring match)")
    parser.add_argument(
        "--sort", "-s",
        choices=["value_delta", "ticker", "account"],
        default="value_delta",
        help="Sort order (default: value_delta, largest changes first)",
    )
    args = parser.parse_args()

    date_a = _parse_date(args.date_a)
    date_b = _parse_date(args.date_b)
    holdings_delta(date_a, date_b, account_filter=args.account, sort_by=args.sort)


if __name__ == "__main__":
    main()
