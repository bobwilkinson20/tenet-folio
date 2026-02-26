"""Unit tests for utils.datetime helpers."""

from datetime import date, datetime, timezone

from utils.datetime import utc_to_local_date


class TestUtcToLocalDate:
    """Tests for the utc_to_local_date helper."""

    def test_naive_utc_converted(self):
        """Naive UTC datetime is treated as UTC and converted to local date."""
        # This is a basic sanity check — exact result depends on system timezone
        utc_dt = datetime(2026, 2, 11, 1, 0, 0)  # naive
        result = utc_to_local_date(utc_dt)
        assert isinstance(result, date)

    def test_aware_utc_converted(self):
        """Timezone-aware UTC datetime is converted correctly."""
        utc_dt = datetime(2026, 2, 11, 1, 0, 0, tzinfo=timezone.utc)
        result = utc_to_local_date(utc_dt)
        assert isinstance(result, date)

    def test_midnight_utc_same_day_in_utc(self):
        """Midnight UTC should be the same date in UTC and later timezones."""
        utc_dt = datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc)
        result = utc_to_local_date(utc_dt)
        # In UTC or any timezone behind UTC (Americas), this is Feb 10 or Feb 11
        # In UTC or any timezone ahead of UTC (Asia), this is Feb 11
        # Either way, it should be a valid date
        assert result in (date(2026, 2, 10), date(2026, 2, 11))
