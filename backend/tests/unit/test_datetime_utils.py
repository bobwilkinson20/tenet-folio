"""Unit tests for utils.date_helpers."""

import os
import time
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from utils.date_helpers import utc_to_local_date


def _with_tz(tz_name: str):
    """Context manager that temporarily sets the system timezone."""
    return patch.dict(os.environ, {"TZ": tz_name})


class TestUtcToLocalDate:
    """Tests for the utc_to_local_date helper."""

    def test_naive_utc_treated_as_utc(self):
        """Naive datetime is treated as UTC — result matches aware equivalent."""
        naive = datetime(2026, 2, 11, 1, 0, 0)
        aware = datetime(2026, 2, 11, 1, 0, 0, tzinfo=timezone.utc)
        assert utc_to_local_date(naive) == utc_to_local_date(aware)

    def test_aware_utc_returns_date(self):
        """Timezone-aware UTC datetime is converted to a date."""
        utc_dt = datetime(2026, 2, 11, 1, 0, 0, tzinfo=timezone.utc)
        result = utc_to_local_date(utc_dt)
        assert isinstance(result, date)


# time.tzset() is Unix-only; skip these on Windows
@pytest.mark.skipif(not hasattr(time, "tzset"), reason="time.tzset() requires Unix")
class TestUtcToLocalDateTimezones:
    """Deterministic timezone-crossing tests using TZ env var."""

    def test_date_boundary_cross_pacific(self):
        """1 AM UTC on Feb 11 should be Feb 10 in US/Pacific (UTC-8)."""
        utc_dt = datetime(2026, 2, 11, 1, 0, 0, tzinfo=timezone.utc)
        with _with_tz("US/Pacific"):
            time.tzset()
            result = utc_to_local_date(utc_dt)
        time.tzset()  # restore
        assert result == date(2026, 2, 10)

    def test_no_date_boundary_cross_tokyo(self):
        """1 AM UTC on Feb 11 should be Feb 11 in Asia/Tokyo (UTC+9)."""
        utc_dt = datetime(2026, 2, 11, 1, 0, 0, tzinfo=timezone.utc)
        with _with_tz("Asia/Tokyo"):
            time.tzset()
            result = utc_to_local_date(utc_dt)
        time.tzset()  # restore
        assert result == date(2026, 2, 11)

    def test_midnight_utc_previous_day_mountain(self):
        """Midnight UTC on Feb 11 should be Feb 10 in US/Mountain (UTC-7)."""
        utc_dt = datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc)
        with _with_tz("US/Mountain"):
            time.tzset()
            result = utc_to_local_date(utc_dt)
        time.tzset()  # restore
        assert result == date(2026, 2, 10)

    def test_midday_utc_same_day_in_far_west(self):
        """1 PM UTC should still be Feb 11 even in UTC-12 (dateline west)."""
        utc_dt = datetime(2026, 2, 11, 13, 0, 0, tzinfo=timezone.utc)
        with _with_tz("Etc/GMT+12"):
            time.tzset()
            result = utc_to_local_date(utc_dt)
        time.tzset()  # restore
        assert result == date(2026, 2, 11)
