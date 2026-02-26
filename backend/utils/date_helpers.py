"""Date/time utilities for working with naive-UTC timestamps."""

from datetime import date, datetime, timezone


def utc_to_local_date(utc_dt: datetime) -> date:
    """Convert a naive-UTC datetime to a local calendar date.

    SyncSession timestamps are stored as naive UTC in SQLite.
    date.today() returns the local date. We need local dates when
    comparing to avoid off-by-one errors (e.g., 5 PM PT on Feb 10
    is stored as Feb 11 01:00 UTC).
    """
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone().date()
