#!/usr/bin/env python
"""Export earliest snapshot per account to JSON for manual editing.

Produces a JSON template based on each account's earliest successful snapshot.
The user edits holdings to reflect Jan 1, 2026 positions, then feeds the file
to import_backfill_snapshot.py.

Usage:
    cd backend
    uv run python -m scripts.export_earliest_snapshots 2026-01-01 [--output FILE]
"""

import argparse
import json
from datetime import timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database import get_session_local
from models import AccountSnapshot, Holding, SyncSession


def _decimal_str(val: Decimal | None) -> str:
    """Format a Decimal for JSON (string to preserve precision)."""
    if val is None:
        return "0"
    return str(val)


def _get_earliest_snapshot_per_account(db: Session) -> list[dict]:
    """Find the earliest successful snapshot for each account and export holdings."""
    # Subquery: earliest completed sync_session timestamp per account
    earliest_sub = (
        db.query(
            AccountSnapshot.account_id,
            func.min(SyncSession.timestamp).label("min_ts"),
        )
        .join(SyncSession, AccountSnapshot.sync_session_id == SyncSession.id)
        .filter(
            SyncSession.is_complete.is_(True),
            AccountSnapshot.status == "success",
        )
        .group_by(AccountSnapshot.account_id)
        .subquery()
    )

    # Join back to get the actual snapshots at those timestamps
    snapshots = (
        db.query(AccountSnapshot)
        .join(SyncSession, AccountSnapshot.sync_session_id == SyncSession.id)
        .join(
            earliest_sub,
            (AccountSnapshot.account_id == earliest_sub.c.account_id)
            & (SyncSession.timestamp == earliest_sub.c.min_ts),
        )
        .options(
            joinedload(AccountSnapshot.account),
            joinedload(AccountSnapshot.holdings).joinedload(Holding.security),
            joinedload(AccountSnapshot.sync_session),
        )
        .all()
    )

    accounts_out = []
    for snap in snapshots:
        acct = snap.account
        ts = snap.sync_session.timestamp
        # Convert naive UTC timestamp to date string
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        snapshot_date_str = ts.strftime("%Y-%m-%d")

        holdings_out = []
        for h in sorted(snap.holdings, key=lambda x: x.ticker):
            holdings_out.append({
                "ticker": h.ticker,
                "security_name": h.security.name if h.security else None,
                "security_id": h.security_id,
                "quantity": _decimal_str(h.quantity),
                "snapshot_price": _decimal_str(h.snapshot_price),
                "snapshot_value": _decimal_str(h.snapshot_value),
            })

        accounts_out.append({
            "account_id": acct.id,
            "account_name": acct.name,
            "provider_name": acct.provider_name,
            "institution_name": acct.institution_name,
            "earliest_snapshot_date": snapshot_date_str,
            "total_value": _decimal_str(snap.total_value),
            "holdings": holdings_out,
        })

    # Sort by account name for readability
    accounts_out.sort(key=lambda a: a["account_name"] or "")
    return accounts_out


def export_snapshots(output_path: str, snapshot_date: str):
    """Export earliest snapshots to JSON file."""
    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        accounts = _get_earliest_snapshot_per_account(db)

        payload = {
            "snapshot_date": snapshot_date,
            "_instructions": (
                "Edit this file to reflect holdings as of the snapshot_date. "
                "For each account: add, remove, or adjust holdings. "
                "You can change quantity and snapshot_price; snapshot_value "
                "will be recalculated on import. For new tickers not already "
                "in the system, set security_id to null and the import script "
                "will create the Security record. Run the import with: "
                "python -m scripts.import_backfill_snapshot <this_file>"
            ),
            "accounts": accounts,
        }

        with open(output_path, "w") as f:
            json.dump(payload, f, indent=2)

        print(f"Exported {len(accounts)} accounts to {output_path}")
        for acct in accounts:
            n_holdings = len(acct["holdings"])
            print(f"  {acct['account_name']} ({acct['provider_name']}): "
                  f"{n_holdings} holdings, earliest snapshot {acct['earliest_snapshot_date']}")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Export earliest snapshots to JSON")
    parser.add_argument(
        "snapshot_date",
        help="Target date for the backfill snapshot (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output", "-o",
        default="backfill_snapshot.json",
        help="Output JSON file path (default: backfill_snapshot.json)",
    )
    args = parser.parse_args()
    export_snapshots(args.output, args.snapshot_date)


if __name__ == "__main__":
    main()
