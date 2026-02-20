"""Shared datetime parsing utilities for provider clients.

Centralises the date/time parsing logic that all provider integrations need:
ISO 8601 strings, Unix timestamps, timezone normalisation, etc.
"""

from datetime import date, datetime, timezone


def parse_iso_datetime(value) -> datetime | None:
    """Parse an ISO 8601 string (or date/datetime object) to a UTC-aware datetime.

    Handles the formats produced by each provider:
    - Z suffix (Coinbase: "2024-01-15T10:30:00Z")
    - +0000 no-colon offset (Schwab: "2024-01-15T10:30:00+0000")
    - Standard ISO with colon offset (SnapTrade: "2024-06-28 18:42:46+00:00")
    - Date-only strings (SnapTrade: "2024-06-28")
    - datetime/date objects passed through with UTC normalisation

    Args:
        value: A string, date, datetime, or None.

    Returns:
        A timezone-aware UTC datetime, or None if the value cannot be parsed.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)

    value_str = str(value)

    # Handle Z suffix: "2024-01-15T10:30:00Z" -> "2024-01-15T10:30:00+00:00"
    if value_str.endswith("Z"):
        value_str = value_str[:-1] + "+00:00"

    # Handle "+0000" no-colon tz: "...+0000" -> "...+00:00"
    if (
        len(value_str) >= 5
        and value_str[-5] in ("+", "-")
        and value_str[-4:].isdigit()
    ):
        value_str = value_str[:-2] + ":" + value_str[-2:]

    try:
        dt = datetime.fromisoformat(value_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass

    # Try date-only: "2024-06-28"
    try:
        d = date.fromisoformat(str(value))
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def parse_unix_timestamp(value) -> datetime | None:
    """Parse a Unix epoch timestamp to a UTC-aware datetime.

    Args:
        value: An int, float, string-encoded number, or None.

    Returns:
        A timezone-aware UTC datetime, or None if the value cannot be parsed.
    """
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC).

    If the datetime is naive, attach UTC; otherwise return as-is.

    Args:
        dt: A datetime object.

    Returns:
        The same datetime, guaranteed to be timezone-aware.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def date_to_datetime(d: date) -> datetime:
    """Convert a date to a midnight-UTC datetime.

    Args:
        d: A date object.

    Returns:
        A timezone-aware datetime at midnight UTC on that date.
    """
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
