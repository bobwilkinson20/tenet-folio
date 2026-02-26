"""Unit tests for utils.date_helpers."""

import os
import time
from datetime import date, datetime, timezone
import pytest

from utils.date_helpers import utc_to_local_date


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

    @pytest.fixture(autouse=True)
    def _restore_tz(self):
        """Restore the system timezone after each test, even on failure."""
        original_tz = os.environ.get("TZ")
        yield
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        time.tzset()

    @staticmethod
    def _set_tz(tz_name: str):
        os.environ["TZ"] = tz_name
        time.tzset()

    def test_date_boundary_cross_pacific(self):
        """1 AM UTC on Feb 11 should be Feb 10 in US/Pacific (UTC-8)."""
        utc_dt = datetime(2026, 2, 11, 1, 0, 0, tzinfo=timezone.utc)
        self._set_tz("US/Pacific")
        assert utc_to_local_date(utc_dt) == date(2026, 2, 10)

    def test_no_date_boundary_cross_tokyo(self):
        """1 AM UTC on Feb 11 should be Feb 11 in Asia/Tokyo (UTC+9)."""
        utc_dt = datetime(2026, 2, 11, 1, 0, 0, tzinfo=timezone.utc)
        self._set_tz("Asia/Tokyo")
        assert utc_to_local_date(utc_dt) == date(2026, 2, 11)

    def test_midnight_utc_previous_day_mountain(self):
        """Midnight UTC on Feb 11 should be Feb 10 in US/Mountain (UTC-7)."""
        utc_dt = datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc)
        self._set_tz("US/Mountain")
        assert utc_to_local_date(utc_dt) == date(2026, 2, 10)

    def test_midday_utc_same_day_in_far_west(self):
        """1 PM UTC should still be Feb 11 even in UTC-12 (dateline west)."""
        utc_dt = datetime(2026, 2, 11, 13, 0, 0, tzinfo=timezone.utc)
        self._set_tz("Etc/GMT+12")
        assert utc_to_local_date(utc_dt) == date(2026, 2, 11)
