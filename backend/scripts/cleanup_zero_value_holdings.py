#!/usr/bin/env python
"""Clean up zero-value synthetic holdings.

This script removes holdings with synthetic tickers (_SF:*) that have zero
market value. These were created before the fix that filters out zero-value
holdings without ticker symbols.

Also removes orphaned Security records for synthetic tickers that no longer
have any associated holdings.

Usage:
    python -m scripts.cleanup_zero_value_holdings
    python -m scripts.cleanup_zero_value_holdings --dry-run
"""

import argparse
from decimal import Decimal

from database import get_session_local
from models import Holding, Security


def cleanup_zero_value_holdings(dry_run: bool = False):
    """Remove zero-value synthetic holdings and orphaned securities."""
    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        # Find zero-value holdings with synthetic tickers
        zero_value_holdings = (
            db.query(Holding)
            .filter(
                Holding.ticker.like("_SF:%"),
                Holding.market_value <= Decimal("0"),
            )
            .all()
        )

        print(f"Found {len(zero_value_holdings)} zero-value synthetic holdings")

        if zero_value_holdings:
            # Collect affected tickers before deletion
            affected_tickers = {h.ticker for h in zero_value_holdings}

            if dry_run:
                print("\n[DRY RUN] Would delete these holdings:")
                for h in zero_value_holdings:
                    print(f"  - {h.ticker} (value: ${h.market_value})")
            else:
                for h in zero_value_holdings:
                    print(f"  Deleting: {h.ticker} (value: ${h.market_value})")
                    db.delete(h)
                db.flush()

            # Check for orphaned securities (synthetic tickers with no remaining holdings)
            orphaned_securities = []
            for ticker in affected_tickers:
                remaining = db.query(Holding).filter_by(ticker=ticker).count()
                if remaining == 0:
                    security = db.query(Security).filter_by(ticker=ticker).first()
                    if security:
                        orphaned_securities.append(security)

            if orphaned_securities:
                print(f"\nFound {len(orphaned_securities)} orphaned synthetic securities")
                if dry_run:
                    print("[DRY RUN] Would delete these securities:")
                    for s in orphaned_securities:
                        print(f"  - {s.ticker}: {s.name}")
                else:
                    for s in orphaned_securities:
                        print(f"  Deleting security: {s.ticker}")
                        db.delete(s)

        if not dry_run:
            db.commit()
            print("\nCleanup complete!")
        else:
            print("\n[DRY RUN] No changes made. Run without --dry-run to apply.")

        # Summary
        print("\nSummary:")
        print(f"  Holdings removed: {len(zero_value_holdings)}")
        if zero_value_holdings:
            print(f"  Securities removed: {len(orphaned_securities)}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean up zero-value synthetic holdings"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without making changes",
    )
    args = parser.parse_args()

    cleanup_zero_value_holdings(dry_run=args.dry_run)
