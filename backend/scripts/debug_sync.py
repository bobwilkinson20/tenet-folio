#!/usr/bin/env python
"""Manual sync script for troubleshooting provider data.

Runs a single-provider sync with exhaustive debug output.
Dry-run by default (fetch + display only); pass --write to persist to DB.

Usage:
    python -m scripts.debug_sync --provider SnapTrade
    python -m scripts.debug_sync --provider SimpleFIN --verbose
    python -m scripts.debug_sync --provider IBKR --debug
    python -m scripts.debug_sync --provider Coinbase --debug --write
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime
from decimal import Decimal

from integrations.provider_protocol import (
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncResult,
)
from models import Account, SyncSession
from models.sync_log import SyncLogEntry
from services.activity_service import ActivityService
from services.sync_service import SyncService

# Verbosity levels
SUMMARY = 0
VERBOSE = 1
DEBUG = 2

# Canonical provider names (lowercase key -> canonical value)
PROVIDER_NAMES = {
    "snaptrade": "SnapTrade",
    "simplefin": "SimpleFIN",
    "ibkr": "IBKR",
    "coinbase": "Coinbase",
    "schwab": "Schwab",
}


def get_provider_client(name: str):
    """Map a provider name to a client instance.

    Args:
        name: Provider name (case-insensitive).

    Returns:
        A provider client instance.

    Exits with error if the provider name is invalid or not configured.
    """
    canonical = PROVIDER_NAMES.get(name.lower())
    if not canonical:
        valid = ", ".join(PROVIDER_NAMES.values())
        print(f"Error: Unknown provider '{name}'. Valid providers: {valid}")
        sys.exit(1)

    # Import and instantiate the specific client
    if canonical == "SnapTrade":
        from integrations.snaptrade_client import SnapTradeClient

        client = SnapTradeClient()
    elif canonical == "SimpleFIN":
        from integrations.simplefin_client import SimpleFINClient

        client = SimpleFINClient()
    elif canonical == "IBKR":
        from integrations.ibkr_flex_client import IBKRFlexClient

        client = IBKRFlexClient()
    elif canonical == "Coinbase":
        from integrations.coinbase_client import CoinbaseClient

        client = CoinbaseClient()
    elif canonical == "Schwab":
        from integrations.schwab_client import SchwabClient

        client = SchwabClient()
    else:
        raise ValueError(f"Unhandled provider: {canonical}")

    if not client.is_configured():
        print(f"Error: {canonical} is not configured.")
        print("Run the setup script or check your .env file.")
        sys.exit(1)

    return client


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n=== {title} ===")


def print_errors(errors: list[str]) -> None:
    """Print provider errors (always shown)."""
    if not errors:
        return
    print_section(f"Provider Errors ({len(errors)})")
    for i, err in enumerate(errors, 1):
        print(f"  [{i}] {err}")


def _fmt_money(value: Decimal | None) -> str:
    """Format a Decimal as a dollar amount."""
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def print_accounts(accounts: list[ProviderAccount], verbosity: int) -> None:
    """Print account information at the given verbosity level."""
    print_section(f"Accounts ({len(accounts)})")
    if verbosity == SUMMARY:
        return

    for i, acct in enumerate(accounts, 1):
        if verbosity == VERBOSE:
            num = f" ({acct.account_number})" if acct.account_number else ""
            print(f"  [{i}] {acct.id} | {acct.institution} | {acct.name}{num}")
        elif verbosity == DEBUG:
            print(f"  Account {i}:")
            print(f"    id: {acct.id}")
            print(f"    name: {acct.name}")
            print(f"    institution: {acct.institution}")
            print(f"    account_number: {acct.account_number}")


def print_holdings(holdings: list[ProviderHolding], verbosity: int) -> None:
    """Print holdings grouped by account at the given verbosity level."""
    total_value = sum(h.market_value for h in holdings)
    print_section(f"Holdings ({len(holdings)})")
    print(f"  Total market value: {_fmt_money(total_value)}")

    if verbosity == SUMMARY:
        return

    # Group by account
    by_account: dict[str, list[ProviderHolding]] = {}
    for h in holdings:
        by_account.setdefault(h.account_id, []).append(h)

    for acct_id, acct_holdings in by_account.items():
        acct_total = sum(h.market_value for h in acct_holdings)
        print(
            f"\n  Account: {acct_id} — "
            f"{len(acct_holdings)} holdings, {_fmt_money(acct_total)}"
        )

        for j, h in enumerate(acct_holdings, 1):
            if verbosity == VERBOSE:
                cost_str = _fmt_money(h.cost_basis) if h.cost_basis is not None else "N/A"
                print(
                    f"    {h.symbol:<12} "
                    f"{h.quantity:>12,.6f} @ {_fmt_money(h.price)} = "
                    f"{_fmt_money(h.market_value)} | cost: {cost_str}"
                )
            elif verbosity == DEBUG:
                print(f"    Holding {j}:")
                print(f"      account_id: {h.account_id}")
                print(f"      symbol: {h.symbol}")
                print(f"      quantity: {h.quantity}")
                print(f"      price: {h.price}")
                print(f"      market_value: {h.market_value}")
                print(f"      currency: {h.currency}")
                print(f"      name: {h.name}")
                print(f"      cost_basis: {h.cost_basis}")
                if h.raw_data:
                    try:
                        raw_json = json.dumps(h.raw_data, indent=2, default=str)
                    except (TypeError, ValueError):
                        raw_json = str(h.raw_data)
                    print(f"      raw_data: {raw_json}")


def print_activities(activities: list[ProviderActivity], verbosity: int) -> None:
    """Print activities with type breakdown at the given verbosity level."""
    type_counts = Counter(a.type for a in activities)
    breakdown = ", ".join(f"{t}: {c}" for t, c in sorted(type_counts.items()))

    print_section(f"Activities ({len(activities)})")
    if breakdown:
        print(f"  {breakdown}")

    if verbosity == SUMMARY:
        return

    for i, a in enumerate(activities, 1):
        if verbosity == VERBOSE:
            ticker_str = f" | {a.ticker}" if a.ticker else ""
            amount_str = f" | {_fmt_money(a.amount)}" if a.amount is not None else ""
            date_str = a.activity_date.strftime("%Y-%m-%d")
            print(
                f"  [{i}] {date_str} | {a.type:<12}{ticker_str}{amount_str}"
            )
        elif verbosity == DEBUG:
            print(f"  Activity {i}:")
            print(f"    external_id: {a.external_id}")
            print(f"    account_id: {a.account_id}")
            print(f"    activity_date: {a.activity_date}")
            print(f"    type: {a.type}")
            print(f"    ticker: {a.ticker}")
            print(f"    units: {a.units}")
            print(f"    price: {a.price}")
            print(f"    amount: {a.amount}")
            print(f"    currency: {a.currency}")
            print(f"    fee: {a.fee}")
            print(f"    description: {a.description}")
            if a.raw_data:
                try:
                    raw_json = json.dumps(a.raw_data, indent=2, default=str)
                except (TypeError, ValueError):
                    raw_json = str(a.raw_data)
                print(f"    raw_data: {raw_json}")


def print_balance_dates(
    balance_dates: dict[str, datetime | None], verbosity: int
) -> None:
    """Print balance dates if any are present."""
    if not balance_dates:
        return
    print_section(f"Balance Dates ({len(balance_dates)})")
    for acct_id, bd in balance_dates.items():
        date_str = bd.strftime("%Y-%m-%d %H:%M:%S %Z") if bd else "None"
        print(f"  {acct_id}: {date_str}")


def print_sync_result(result: ProviderSyncResult, verbosity: int) -> None:
    """Print all sections of a sync result."""
    print_errors(result.errors)
    print_accounts(result.accounts, verbosity)
    print_holdings(result.holdings, verbosity)
    print_balance_dates(result.balance_dates, verbosity)
    print_activities(result.activities, verbosity)


def run_db_sync(
    provider_name: str,
    result: ProviderSyncResult,
    verbosity: int,
) -> None:
    """Write sync results to the database with debug output.

    Replays the SyncService flow: create sync session, upsert accounts,
    sync holdings, sync activities.

    Args:
        provider_name: Canonical provider name.
        result: The ProviderSyncResult from sync_all().
        verbosity: Output verbosity level.
    """
    from database import get_session_local

    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        print_section("Writing to Database")
        sync_service = SyncService()

        # Create sync session
        print("  Creating sync session...")
        sync_session = SyncSession(is_complete=False)
        db.add(sync_session)
        db.flush()

        # Upsert accounts
        print("  Upserting accounts:")
        existing_ids = set()
        if result.accounts:
            # Check which accounts already exist
            for acct in result.accounts:
                existing = (
                    db.query(Account)
                    .filter_by(
                        provider_name=provider_name,
                        external_id=acct.id,
                    )
                    .first()
                )
                if existing:
                    existing_ids.add(acct.id)

            upserted = sync_service._upsert_accounts(
                db, provider_name, result.accounts
            )

            for acct in upserted:
                status = (
                    "UPDATED" if acct.external_id in existing_ids else "CREATED"
                )
                print(f"    {acct.external_id} ({acct.name}): {status}")

        # Group holdings by account
        holdings_by_account: dict[str, list[ProviderHolding]] = {}
        for h in result.holdings:
            holdings_by_account.setdefault(h.account_id, []).append(h)

        # Sync holdings for each account
        accounts = (
            db.query(Account)
            .filter(
                Account.provider_name == provider_name,
                Account.is_active.is_(True),
            )
            .all()
        )

        print("  Syncing holdings:")
        synced_count = 0
        for account in accounts:
            acct_holdings = holdings_by_account.get(account.external_id, [])
            acct_total = sum(h.market_value for h in acct_holdings)
            success = sync_service.sync_account(
                db,
                account,
                sync_session,
                holdings_by_account,
                balance_dates=result.balance_dates,
            )
            status = "OK" if success else "FAILED"
            print(
                f"    {account.name}: "
                f"{len(acct_holdings)} holdings, "
                f"{_fmt_money(acct_total)} [{status}]"
            )
            if success:
                synced_count += 1

        # Sync activities
        if result.activities:
            activities_by_account: dict[str, list[ProviderActivity]] = {}
            for a in result.activities:
                activities_by_account.setdefault(a.account_id, []).append(a)

            print("  Syncing activities:")
            for account in accounts:
                acct_activities = activities_by_account.get(
                    account.external_id, []
                )
                if acct_activities:
                    new_count = ActivityService.sync_activities(
                        db, provider_name, account, acct_activities
                    )
                    dup_count = len(acct_activities) - new_count
                    print(
                        f"    {account.name}: "
                        f"{new_count} new, {dup_count} duplicates skipped"
                    )

        # Create sync log entry
        provider_errors = result.errors
        if provider_errors and synced_count > 0:
            status = "partial"
        elif provider_errors:
            status = "failed"
        else:
            status = "success"

        log_entry = SyncLogEntry(
            sync_session_id=sync_session.id,
            provider_name=provider_name,
            status=status,
            error_messages=provider_errors if provider_errors else None,
            accounts_synced=synced_count,
        )
        db.add(log_entry)

        sync_session.is_complete = synced_count > 0
        db.commit()
        print(f"  Committed. Sync session ID: {sync_session.id}")

    except Exception as e:
        db.rollback()
        print(f"  Error writing to database: {e}")
        raise
    finally:
        db.close()


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse args and orchestrate the sync."""
    parser = argparse.ArgumentParser(
        description="Debug sync script — fetch and inspect provider data.",
    )
    parser.add_argument(
        "--provider",
        required=True,
        help="Provider name: SnapTrade, SimpleFIN, IBKR, Coinbase, Schwab",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show one-line-per-item summaries",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Full detail: all fields on every item + raw_data JSON dumps",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually write to the database (creates SyncSession, upserts accounts, etc.)",
    )

    args = parser.parse_args(argv)

    # Determine verbosity
    if args.debug:
        verbosity = DEBUG
    elif args.verbose:
        verbosity = VERBOSE
    else:
        verbosity = SUMMARY

    # Resolve canonical provider name
    canonical = PROVIDER_NAMES.get(args.provider.lower())
    if not canonical:
        valid = ", ".join(PROVIDER_NAMES.values())
        print(f"Error: Unknown provider '{args.provider}'. Valid providers: {valid}")
        sys.exit(1)

    # Get provider client
    client = get_provider_client(args.provider)

    # Print header
    mode_parts = []
    if verbosity == VERBOSE:
        mode_parts.append("verbose")
    elif verbosity == DEBUG:
        mode_parts.append("debug")
    mode_parts.append("write" if args.write else "dry-run")
    mode_str = ", ".join(mode_parts)

    print(f"Provider: {canonical}")
    print(f"Mode: {mode_str}")
    print("-" * 60)

    # Fetch data
    print("Fetching data from provider...")
    start = time.time()
    try:
        result = client.sync_all()
    except Exception as e:
        print(f"\nError fetching data: {e}")
        sys.exit(1)
    elapsed = time.time() - start
    print(f"Fetched in {elapsed:.2f}s")

    # Display results
    print_sync_result(result, verbosity)

    # Write to DB if requested
    if args.write:
        run_db_sync(canonical, result, verbosity)

    # Summary
    print_section("Summary")
    print(f"  Provider: {canonical}")
    print(f"  Accounts: {len(result.accounts)}")
    print(f"  Holdings: {len(result.holdings)}")
    print(f"  Activities: {len(result.activities)}")
    print(f"  Errors: {len(result.errors)}")
    print(f"  Fetch time: {elapsed:.2f}s")
    if not args.write:
        print("  (Dry-run — no database changes. Use --write to persist.)")


if __name__ == "__main__":
    main()
