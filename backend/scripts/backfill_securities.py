#!/usr/bin/env python
"""Backfill Security records from existing holdings.

This script creates Security records for any tickers that exist in Holdings
but don't have a corresponding Security record. This is useful when:
1. Holdings were synced before the Security auto-creation feature was added
2. Manual data migration scenarios

Usage:
    python -m scripts.backfill_securities
"""

from database import get_session_local
from models import Holding, Security


def backfill_securities():
    """Create Security records for all tickers in holdings."""
    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        # Get all unique tickers from holdings
        holdings = db.query(Holding.ticker).distinct().all()
        tickers = [h[0] for h in holdings]

        print(f"Found {len(tickers)} unique tickers in holdings")

        created = 0
        skipped = 0

        for ticker in tickers:
            # Check if security already exists
            existing = db.query(Security).filter_by(ticker=ticker).first()
            if not existing:
                security = Security(ticker=ticker, name=ticker)
                db.add(security)
                created += 1
                print(f"✓ Created Security for {ticker}")
            else:
                skipped += 1

        db.commit()

        print("\nSummary:")
        print(f"  Created: {created}")
        print(f"  Skipped (already existed): {skipped}")
        print(f"  Total securities: {created + skipped}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    backfill_securities()
