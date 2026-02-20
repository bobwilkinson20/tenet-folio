#!/usr/bin/env python
"""Diagnose and repair DHV (DailyHoldingValue) gaps.

Two modes:
  --diagnose (default): Print per-account DHV gap analysis
  --repair:             Run full_backfill() to fill all gaps from scratch

Usage:
    python -m scripts.dhv_diagnostics              # diagnose
    python -m scripts.dhv_diagnostics --diagnose   # diagnose (explicit)
    python -m scripts.dhv_diagnostics --repair     # repair gaps
"""

import argparse

from database import get_session_local
from services.portfolio_valuation_service import PortfolioValuationService


def diagnose():
    """Print per-account DHV gap analysis."""
    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        service = PortfolioValuationService()
        gaps = service.diagnose_gaps(db)

        if not gaps:
            print("No active accounts with snapshots found.")
            return

        total_missing = 0
        total_partial = 0
        for gap in gaps:
            has_missing = gap["missing_days"] > 0
            has_partial = gap.get("partial_days", 0) > 0
            if has_missing:
                status = "GAPS"
            elif has_partial:
                status = "PARTIAL"
            else:
                status = "OK"
            print(
                f"[{status}] {gap['account_name']}: "
                f"{gap['actual_days']}/{gap['expected_days']} days "
                f"({gap['expected_start']} to {gap['expected_end']})"
            )
            if has_missing:
                total_missing += gap["missing_days"]
                dates_str = ", ".join(gap["missing_dates"][:20])
                suffix = (
                    f" ... and {gap['missing_days'] - 20} more"
                    if gap["missing_days"] > 20
                    else ""
                )
                print(f"       Missing {gap['missing_days']} days: {dates_str}{suffix}")
            if has_partial:
                partial_days = gap["partial_days"]
                total_partial += partial_days
                dates_str = ", ".join(gap.get("partial_dates", [])[:20])
                suffix = (
                    f" ... and {partial_days - 20} more"
                    if partial_days > 20
                    else ""
                )
                print(f"       Partial {partial_days} days: {dates_str}{suffix}")

        print(f"\nTotal missing days: {total_missing}, partial days: {total_partial}")
        if total_missing > 0 or total_partial > 0:
            print("Run with --repair to fill gaps.")
    finally:
        db.close()


def repair():
    """Run full backfill to fill all DHV gaps."""
    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        service = PortfolioValuationService()
        print("Running full backfill...")
        result = service.full_backfill(db, repair=True)

        if result.dates_calculated == 0:
            print("Nothing to backfill.")
        else:
            print("Backfill complete:")
            print(f"  Date range: {result.start_date} to {result.end_date}")
            print(f"  Days calculated: {result.dates_calculated}")
            print(f"  Holdings written: {result.holdings_written}")
            if result.errors:
                print(f"  Errors: {len(result.errors)}")
                for err in result.errors:
                    print(f"    - {err}")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose and repair DHV gaps"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--diagnose",
        action="store_true",
        help="Print per-account DHV gap analysis (default)",
    )
    group.add_argument(
        "--repair",
        action="store_true",
        help="Run full backfill to fill all gaps",
    )

    args = parser.parse_args()

    if args.repair:
        repair()
    else:
        diagnose()


if __name__ == "__main__":
    main()
