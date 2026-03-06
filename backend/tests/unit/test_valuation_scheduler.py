"""Tests for the valuation scheduler background task."""

import asyncio
from dataclasses import dataclass, field
from datetime import date
from unittest.mock import MagicMock, patch

from services.valuation_scheduler import (
    _backfill_lock,
    backfill_loop,
    run_backfill_if_needed,
)


@dataclass
class FakeBackfillResult:
    dates_calculated: int = 0
    holdings_written: int = 0
    errors: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# run_backfill_if_needed
# ---------------------------------------------------------------------------

class TestRunBackfillIfNeeded:
    """Tests for the synchronous run_backfill_if_needed function."""

    @patch("services.valuation_scheduler.date")
    def test_skips_if_already_ran_today(self, mock_date):
        today = date(2026, 3, 6)
        mock_date.today.return_value = today

        result = run_backfill_if_needed(today)

        assert result == today

    @patch("services.valuation_scheduler.SyncService")
    @patch("services.valuation_scheduler.PortfolioValuationService")
    @patch("services.valuation_scheduler.get_session_local")
    @patch("services.valuation_scheduler.date")
    def test_runs_backfill_and_returns_today(
        self, mock_date, mock_get_session, mock_pvs_cls, mock_sync_cls
    ):
        yesterday = date(2026, 3, 5)
        today = date(2026, 3, 6)
        mock_date.today.return_value = today

        mock_sync_cls.is_sync_in_progress.return_value = False

        mock_db = MagicMock()
        mock_session_local = MagicMock(return_value=mock_db)
        mock_get_session.return_value = mock_session_local

        mock_service = MagicMock()
        mock_service.backfill.return_value = FakeBackfillResult(
            dates_calculated=2, holdings_written=10
        )
        mock_pvs_cls.return_value = mock_service

        result = run_backfill_if_needed(yesterday)

        assert result == today
        mock_service.backfill.assert_called_once_with(mock_db)
        mock_db.close.assert_called_once()

    @patch("services.valuation_scheduler.SyncService")
    @patch("services.valuation_scheduler.get_session_local")
    @patch("services.valuation_scheduler.date")
    def test_skips_if_sync_in_progress(
        self, mock_date, mock_get_session, mock_sync_cls
    ):
        yesterday = date(2026, 3, 5)
        today = date(2026, 3, 6)
        mock_date.today.return_value = today
        mock_sync_cls.is_sync_in_progress.return_value = True

        result = run_backfill_if_needed(yesterday)

        assert result == yesterday
        # Should not have opened a DB session
        mock_get_session.assert_not_called()

    @patch("services.valuation_scheduler.date")
    def test_skips_if_lock_held(self, mock_date):
        today = date(2026, 3, 6)
        yesterday = date(2026, 3, 5)
        mock_date.today.return_value = today

        # Hold the lock in another thread
        _backfill_lock.acquire()
        try:
            result = run_backfill_if_needed(yesterday)
            assert result == yesterday
        finally:
            _backfill_lock.release()

    @patch("services.valuation_scheduler.SyncService")
    @patch("services.valuation_scheduler.PortfolioValuationService")
    @patch("services.valuation_scheduler.get_session_local")
    @patch("services.valuation_scheduler.date")
    def test_returns_last_run_date_on_exception(
        self, mock_date, mock_get_session, mock_pvs_cls, mock_sync_cls
    ):
        yesterday = date(2026, 3, 5)
        today = date(2026, 3, 6)
        mock_date.today.return_value = today
        mock_sync_cls.is_sync_in_progress.return_value = False

        mock_db = MagicMock()
        mock_get_session.return_value = MagicMock(return_value=mock_db)

        mock_service = MagicMock()
        mock_service.backfill.side_effect = RuntimeError("boom")
        mock_pvs_cls.return_value = mock_service

        result = run_backfill_if_needed(yesterday)

        assert result == yesterday
        mock_db.close.assert_called_once()

    @patch("services.valuation_scheduler.SyncService")
    @patch("services.valuation_scheduler.PortfolioValuationService")
    @patch("services.valuation_scheduler.get_session_local")
    @patch("services.valuation_scheduler.date")
    def test_closes_db_session_on_failure(
        self, mock_date, mock_get_session, mock_pvs_cls, mock_sync_cls
    ):
        today = date(2026, 3, 6)
        mock_date.today.return_value = today
        mock_sync_cls.is_sync_in_progress.return_value = False

        mock_db = MagicMock()
        mock_get_session.return_value = MagicMock(return_value=mock_db)

        mock_service = MagicMock()
        mock_service.backfill.side_effect = Exception("db error")
        mock_pvs_cls.return_value = mock_service

        run_backfill_if_needed(None)

        mock_db.close.assert_called_once()

    @patch("services.valuation_scheduler.SyncService")
    @patch("services.valuation_scheduler.PortfolioValuationService")
    @patch("services.valuation_scheduler.get_session_local")
    @patch("services.valuation_scheduler.date")
    def test_runs_when_last_run_date_is_none(
        self, mock_date, mock_get_session, mock_pvs_cls, mock_sync_cls
    ):
        today = date(2026, 3, 6)
        mock_date.today.return_value = today
        mock_sync_cls.is_sync_in_progress.return_value = False

        mock_db = MagicMock()
        mock_get_session.return_value = MagicMock(return_value=mock_db)

        mock_service = MagicMock()
        mock_service.backfill.return_value = FakeBackfillResult()
        mock_pvs_cls.return_value = mock_service

        result = run_backfill_if_needed(None)

        assert result == today
        mock_service.backfill.assert_called_once()


# ---------------------------------------------------------------------------
# backfill_loop
# ---------------------------------------------------------------------------

class TestBackfillLoop:
    """Tests for the async backfill_loop."""

    async def test_stops_on_shutdown_event(self):
        shutdown = asyncio.Event()
        shutdown.set()  # Already set — loop should exit immediately

        with patch(
            "services.valuation_scheduler.run_backfill_if_needed"
        ) as mock_run:
            await backfill_loop(shutdown, startup_date=date(2026, 3, 6))

        # Should not have called backfill since shutdown was immediate
        mock_run.assert_not_called()

    async def test_triggers_backfill_on_wake(self):
        shutdown = asyncio.Event()
        call_count = 0

        async def set_after_one_call():
            nonlocal call_count
            # Wait until the backfill has been called at least once
            while call_count < 1:
                await asyncio.sleep(0.01)
            shutdown.set()

        today = date(2026, 3, 6)

        def fake_backfill(last_run_date):
            nonlocal call_count
            call_count += 1
            return today

        with patch(
            "services.valuation_scheduler.BACKFILL_INTERVAL", 0.05
        ), patch(
            "services.valuation_scheduler.run_backfill_if_needed",
            side_effect=fake_backfill,
        ):
            # Start the shutdown trigger concurrently
            await asyncio.gather(
                backfill_loop(shutdown, startup_date=date(2026, 3, 5)),
                set_after_one_call(),
            )

        assert call_count >= 1

    async def test_continues_on_backfill_exception(self):
        shutdown = asyncio.Event()
        call_count = 0

        async def set_after_two_calls():
            nonlocal call_count
            while call_count < 2:
                await asyncio.sleep(0.01)
            shutdown.set()

        def failing_backfill(last_run_date):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        with patch(
            "services.valuation_scheduler.BACKFILL_INTERVAL", 0.05
        ), patch(
            "services.valuation_scheduler.run_backfill_if_needed",
            side_effect=failing_backfill,
        ):
            await asyncio.gather(
                backfill_loop(shutdown, startup_date=None),
                set_after_two_calls(),
            )

        # Loop survived the exception and ran again
        assert call_count >= 2
