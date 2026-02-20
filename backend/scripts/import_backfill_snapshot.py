#!/usr/bin/env python
"""Import a backfill snapshot from an edited JSON file.

Creates a synthetic SyncSession + AccountSnapshots + Holdings from a JSON file
produced by export_earliest_snapshots.py (after manual editing).

After importing, run the DHV repair to compute daily values:
    uv run python -m scripts.dhv_diagnostics --repair

Usage:
    cd backend
    uv run python -m scripts.import_backfill_snapshot backfill_snapshot.json [--dry-run]
"""

import argparse
import json
import sys
from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from database import get_session_local
from models import Account, AccountSnapshot, Holding, Security, SyncSession


def _parse_decimal(val: str | int | float | None, field_name: str) -> Decimal:
    """Parse a value to Decimal, raising a clear error on failure."""
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except InvalidOperation:
        print(f"  ERROR: Cannot parse '{val}' as decimal for {field_name}")
        sys.exit(1)


def _resolve_security(db, ticker: str, security_id: str | None, security_name: str | None) -> Security:
    """Find or create a Security record for the given ticker."""
    # Try by security_id first
    if security_id:
        sec = db.query(Security).filter(Security.id == security_id).first()
        if sec:
            return sec

    # Try by ticker
    sec = db.query(Security).filter(Security.ticker == ticker).first()
    if sec:
        return sec

    # Create new security
    sec = Security(ticker=ticker, name=security_name or ticker)
    db.add(sec)
    db.flush()  # Assign ID
    print(f"    Created new Security: {ticker} ({security_name or ticker})")
    return sec


def import_snapshot(json_path: str, dry_run: bool = False):
    """Import a backfill snapshot from JSON."""
    with open(json_path) as f:
        data = json.load(f)

    snapshot_date_str = data.get("snapshot_date")
    if not snapshot_date_str:
        print("ERROR: Missing 'snapshot_date' in JSON")
        sys.exit(1)

    try:
        snapshot_date = datetime.strptime(snapshot_date_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERROR: Invalid snapshot_date format: {snapshot_date_str} (expected YYYY-MM-DD)")
        sys.exit(1)

    accounts_data = data.get("accounts", [])
    if not accounts_data:
        print("ERROR: No accounts found in JSON")
        sys.exit(1)

    # Use noon UTC (naive) to avoid timezone day-boundary issues.
    # SyncSession.timestamp is stored as naive UTC in SQLite.
    snapshot_timestamp = datetime.combine(snapshot_date, time(12, 0))

    print(f"Snapshot date: {snapshot_date}")
    print(f"Timestamp (naive UTC): {snapshot_timestamp}")
    print(f"Accounts: {len(accounts_data)}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        # Check for existing sync session at this timestamp
        existing = (
            db.query(SyncSession)
            .filter(SyncSession.timestamp == snapshot_timestamp)
            .first()
        )
        if existing:
            print(f"WARNING: A SyncSession already exists at {snapshot_timestamp}")
            print(f"  ID: {existing.id}, complete: {existing.is_complete}")
            resp = input("  Delete it and re-import? [y/N] ")
            if resp.lower() != "y":
                print("Aborted.")
                return
            # Delete cascading (snapshots → holdings)
            for snap in existing.account_snapshots:
                for h in snap.holdings:
                    db.delete(h)
                db.delete(snap)
            db.delete(existing)
            db.flush()
            print("  Deleted existing session.")
            print()

        # Create SyncSession — timestamp is already naive UTC
        sync_session = SyncSession(
            timestamp=snapshot_timestamp,
            is_complete=True,
        )
        db.add(sync_session)
        db.flush()
        print(f"Created SyncSession: {sync_session.id}")

        total_holdings = 0
        total_accounts = 0

        for acct_data in accounts_data:
            account_id = acct_data.get("account_id")
            account_name = acct_data.get("account_name", "Unknown")

            if not account_id:
                print(f"  SKIP: Missing account_id for '{account_name}'")
                continue

            # Verify account exists
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account:
                print(f"  SKIP: Account not found: {account_id} ({account_name})")
                continue

            holdings_data = acct_data.get("holdings", [])
            print(f"  {account.name}: {len(holdings_data)} holdings")

            # Calculate total value from holdings
            total_value = Decimal("0")
            holding_records = []

            for h_data in holdings_data:
                ticker = h_data.get("ticker")
                if not ticker:
                    print("    SKIP: Missing ticker in holding")
                    continue

                quantity = _parse_decimal(h_data.get("quantity"), f"{ticker}.quantity")
                snapshot_price = _parse_decimal(h_data.get("snapshot_price"), f"{ticker}.snapshot_price")
                snapshot_value = quantity * snapshot_price

                security = _resolve_security(
                    db, ticker,
                    h_data.get("security_id"),
                    h_data.get("security_name"),
                )

                holding_records.append({
                    "security": security,
                    "ticker": ticker,
                    "quantity": quantity,
                    "snapshot_price": snapshot_price,
                    "snapshot_value": snapshot_value,
                })
                total_value += snapshot_value

            # Create AccountSnapshot
            acct_snapshot = AccountSnapshot(
                account_id=account_id,
                sync_session_id=sync_session.id,
                status="success",
                total_value=total_value,
                balance_date=None,
            )
            db.add(acct_snapshot)
            db.flush()

            # Create Holdings
            for rec in holding_records:
                holding = Holding(
                    account_snapshot_id=acct_snapshot.id,
                    security_id=rec["security"].id,
                    ticker=rec["ticker"],
                    quantity=rec["quantity"],
                    snapshot_price=rec["snapshot_price"],
                    snapshot_value=rec["snapshot_value"],
                )
                db.add(holding)
                total_holdings += 1
                print(f"    {rec['ticker']}: {rec['quantity']} @ {rec['snapshot_price']} = {rec['snapshot_value']}")

            total_accounts += 1

        if dry_run:
            db.rollback()
            print(f"\nDRY RUN complete: would create {total_accounts} snapshots, {total_holdings} holdings")
        else:
            db.commit()
            print(f"\nImported: {total_accounts} account snapshots, {total_holdings} holdings")
            print(f"SyncSession ID: {sync_session.id}")
            print()
            print("Next step: run DHV backfill to compute daily values:")
            print("  python -m scripts.dhv_diagnostics --repair")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Import backfill snapshot from JSON")
    parser.add_argument("json_file", help="Path to edited JSON file")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate and show what would be created without writing to DB",
    )
    args = parser.parse_args()
    import_snapshot(args.json_file, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
