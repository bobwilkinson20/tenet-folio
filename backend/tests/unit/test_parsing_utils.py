"""Tests for shared datetime parsing utilities."""

from datetime import date, datetime, timezone, timedelta

from integrations.parsing_utils import (
    date_to_datetime,
    ensure_utc,
    parse_iso_datetime,
    parse_unix_timestamp,
)


class TestParseIsoDatetime:
    """Tests for parse_iso_datetime."""

    def test_none_returns_none(self):
        assert parse_iso_datetime(None) is None

    def test_naive_datetime_gets_utc(self):
        dt = datetime(2024, 6, 28, 12, 0, 0)
        result = parse_iso_datetime(dt)
        assert result.tzinfo == timezone.utc
        assert result == datetime(2024, 6, 28, 12, 0, 0, tzinfo=timezone.utc)

    def test_aware_datetime_passthrough(self):
        dt = datetime(2024, 6, 28, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_iso_datetime(dt)
        assert result is dt

    def test_aware_datetime_other_tz(self):
        """Aware datetimes with non-UTC tz are returned as-is."""
        tz_minus5 = timezone(timedelta(hours=-5))
        dt = datetime(2024, 6, 28, 12, 0, 0, tzinfo=tz_minus5)
        result = parse_iso_datetime(dt)
        assert result is dt
        assert result.tzinfo == tz_minus5

    def test_date_object(self):
        d = date(2024, 6, 28)
        result = parse_iso_datetime(d)
        assert result == datetime(2024, 6, 28, 0, 0, 0, tzinfo=timezone.utc)

    def test_standard_iso_string(self):
        result = parse_iso_datetime("2024-06-28T18:42:46+00:00")
        assert result == datetime(2024, 6, 28, 18, 42, 46, tzinfo=timezone.utc)

    def test_z_suffix(self):
        """Coinbase format: 2024-01-15T10:30:00Z"""
        result = parse_iso_datetime("2024-01-15T10:30:00Z")
        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_no_colon_tz_positive(self):
        """Schwab format: 2024-01-15T10:30:00+0000"""
        result = parse_iso_datetime("2024-01-15T10:30:00+0000")
        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_no_colon_tz_negative(self):
        """Negative offset without colon: 2024-01-15T10:30:00-0500"""
        result = parse_iso_datetime("2024-01-15T10:30:00-0500")
        expected_tz = timezone(timedelta(hours=-5))
        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=expected_tz)

    def test_naive_string_gets_utc(self):
        result = parse_iso_datetime("2024-06-28T18:42:46")
        assert result == datetime(2024, 6, 28, 18, 42, 46, tzinfo=timezone.utc)

    def test_date_only_string(self):
        """SnapTrade date-only: 2024-06-28"""
        result = parse_iso_datetime("2024-06-28")
        assert result == datetime(2024, 6, 28, 0, 0, 0, tzinfo=timezone.utc)

    def test_snaptrade_space_separator(self):
        """SnapTrade: '2024-06-28 18:42:46.561408+00:00'"""
        result = parse_iso_datetime("2024-06-28 18:42:46.561408+00:00")
        assert result is not None
        assert result.tzinfo is not None
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 28

    def test_invalid_string_returns_none(self):
        assert parse_iso_datetime("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert parse_iso_datetime("") is None

    def test_z_suffix_with_microseconds(self):
        result = parse_iso_datetime("2024-01-15T10:30:00.123456Z")
        assert result is not None
        assert result.microsecond == 123456


class TestParseUnixTimestamp:
    """Tests for parse_unix_timestamp."""

    def test_none_returns_none(self):
        assert parse_unix_timestamp(None) is None

    def test_int_timestamp(self):
        # 2024-01-01 00:00:00 UTC = 1704067200
        result = parse_unix_timestamp(1704067200)
        assert result == datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_string_timestamp(self):
        result = parse_unix_timestamp("1704067200")
        assert result == datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_zero_timestamp(self):
        result = parse_unix_timestamp(0)
        assert result == datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_invalid_string_returns_none(self):
        assert parse_unix_timestamp("not-a-number") is None

    def test_float_timestamp(self):
        """Float timestamps are truncated to int."""
        result = parse_unix_timestamp(1704067200.5)
        assert result == datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


class TestEnsureUtc:
    """Tests for ensure_utc."""

    def test_naive_becomes_utc(self):
        dt = datetime(2024, 6, 28, 12, 0, 0)
        result = ensure_utc(dt)
        assert result.tzinfo == timezone.utc

    def test_utc_passthrough(self):
        dt = datetime(2024, 6, 28, 12, 0, 0, tzinfo=timezone.utc)
        result = ensure_utc(dt)
        assert result is dt

    def test_other_tz_passthrough(self):
        """Non-UTC aware datetimes are returned as-is."""
        tz = timezone(timedelta(hours=5))
        dt = datetime(2024, 6, 28, 12, 0, 0, tzinfo=tz)
        result = ensure_utc(dt)
        assert result is dt


class TestDateToDatetime:
    """Tests for date_to_datetime."""

    def test_basic_conversion(self):
        d = date(2024, 6, 28)
        result = date_to_datetime(d)
        assert result == datetime(2024, 6, 28, 0, 0, 0, tzinfo=timezone.utc)
        assert result.tzinfo == timezone.utc

    def test_returns_midnight(self):
        result = date_to_datetime(date(2024, 1, 1))
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
