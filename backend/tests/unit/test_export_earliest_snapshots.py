"""Tests for scripts/export_earliest_snapshots.py."""

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models import Account, AccountSnapshot, Holding, SyncSession
from scripts.export_earliest_snapshots import (
    _decimal_str,
    _get_earliest_snapshot_per_account,
)
from tests.fixtures import get_or_create_security


def _make_account(db: Session, name: str, provider: str = "SnapTrade", ext_id: str = "ext_1") -> Account:
    acct = Account(provider_name=provider, external_id=ext_id, name=name, is_active=True)
    db.add(acct)
    db.flush()
    return acct


def _make_snapshot(
    db: Session,
    account: Account,
    timestamp: datetime,
    holdings: list[tuple[str, Decimal, Decimal]],
    is_complete: bool = True,
    status: str = "success",
) -> tuple[SyncSession, AccountSnapshot]:
    """Create a SyncSession + AccountSnapshot + Holdings.

    holdings: list of (ticker, quantity, price)
    """
    ss = SyncSession(timestamp=timestamp.replace(tzinfo=None), is_complete=is_complete)
    db.add(ss)
    db.flush()

    total = sum(qty * price for _, qty, price in holdings)
    snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=ss.id,
        status=status,
        total_value=total,
    )
    db.add(snap)
    db.flush()

    for ticker, qty, price in holdings:
        sec = get_or_create_security(db, ticker, f"{ticker} Inc.")
        h = Holding(
            account_snapshot_id=snap.id,
            security_id=sec.id,
            ticker=ticker,
            quantity=qty,
            snapshot_price=price,
            snapshot_value=qty * price,
        )
        db.add(h)

    db.flush()
    return ss, snap


class TestDecimalStr:
    def test_none_returns_zero(self):
        assert _decimal_str(None) == "0"

    def test_decimal_value(self):
        assert _decimal_str(Decimal("150.50")) == "150.50"

    def test_zero(self):
        assert _decimal_str(Decimal("0")) == "0"


class TestGetEarliestSnapshotPerAccount:
    def test_empty_db(self, db):
        result = _get_earliest_snapshot_per_account(db)
        assert result == []

    def test_single_account_single_snapshot(self, db):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_snapshot(
            db, acct,
            datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("10"), Decimal("150.00"))],
        )

        result = _get_earliest_snapshot_per_account(db)
        assert len(result) == 1
        assert result[0]["account_name"] == "Test Account"
        assert result[0]["provider_name"] == "SnapTrade"
        assert result[0]["earliest_snapshot_date"] == "2026-02-01"
        assert len(result[0]["holdings"]) == 1
        assert result[0]["holdings"][0]["ticker"] == "AAPL"
        assert Decimal(result[0]["holdings"][0]["quantity"]) == Decimal("10")

    def test_picks_earliest_snapshot(self, db):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_snapshot(
            db, acct,
            datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("5"), Decimal("140.00"))],
        )
        _make_snapshot(
            db, acct,
            datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("10"), Decimal("150.00"))],
        )

        result = _get_earliest_snapshot_per_account(db)
        assert len(result) == 1
        assert result[0]["earliest_snapshot_date"] == "2026-01-01"
        assert Decimal(result[0]["holdings"][0]["quantity"]) == Decimal("5")

    def test_skips_incomplete_sync_session(self, db):
        acct = _make_account(db, "Test Account", ext_id="e1")
        # Incomplete (earlier)
        _make_snapshot(
            db, acct,
            datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("5"), Decimal("140.00"))],
            is_complete=False,
        )
        # Complete (later)
        _make_snapshot(
            db, acct,
            datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("10"), Decimal("150.00"))],
        )

        result = _get_earliest_snapshot_per_account(db)
        assert len(result) == 1
        assert result[0]["earliest_snapshot_date"] == "2026-02-01"

    def test_skips_failed_snapshots(self, db):
        acct = _make_account(db, "Test Account", ext_id="e1")
        # Failed (earlier)
        _make_snapshot(
            db, acct,
            datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("5"), Decimal("140.00"))],
            status="failed",
        )
        # Success (later)
        _make_snapshot(
            db, acct,
            datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("10"), Decimal("150.00"))],
        )

        result = _get_earliest_snapshot_per_account(db)
        assert len(result) == 1
        assert result[0]["earliest_snapshot_date"] == "2026-02-01"

    def test_multiple_accounts_sorted_by_name(self, db):
        acct_b = _make_account(db, "Bravo Account", ext_id="e2")
        acct_a = _make_account(db, "Alpha Account", ext_id="e1")

        _make_snapshot(
            db, acct_b,
            datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            [("GOOG", Decimal("3"), Decimal("180.00"))],
        )
        _make_snapshot(
            db, acct_a,
            datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("10"), Decimal("150.00"))],
        )

        result = _get_earliest_snapshot_per_account(db)
        assert len(result) == 2
        assert result[0]["account_name"] == "Alpha Account"
        assert result[1]["account_name"] == "Bravo Account"

    def test_holdings_sorted_by_ticker(self, db):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_snapshot(
            db, acct,
            datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            [
                ("GOOG", Decimal("3"), Decimal("180.00")),
                ("AAPL", Decimal("10"), Decimal("150.00")),
            ],
        )

        result = _get_earliest_snapshot_per_account(db)
        assert result[0]["holdings"][0]["ticker"] == "AAPL"
        assert result[0]["holdings"][1]["ticker"] == "GOOG"

    def test_includes_security_metadata(self, db):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_snapshot(
            db, acct,
            datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("10"), Decimal("150.00"))],
        )

        result = _get_earliest_snapshot_per_account(db)
        holding = result[0]["holdings"][0]
        assert holding["security_name"] == "AAPL Inc."
        assert holding["security_id"] is not None
        assert Decimal(holding["snapshot_price"]) == Decimal("150.00")
        assert Decimal(holding["snapshot_value"]) == Decimal("1500.00")


class TestExportSnapshots:
    def test_writes_json_file(self, db, tmp_path, monkeypatch):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_snapshot(
            db, acct,
            datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            [("AAPL", Decimal("10"), Decimal("150.00"))],
        )

        monkeypatch.setattr(
            "scripts.export_earliest_snapshots.get_session_local",
            lambda: lambda: db,
        )
        # Prevent the monkeypatched session from being closed
        monkeypatch.setattr(db, "close", lambda: None)

        from scripts.export_earliest_snapshots import export_snapshots
        output_path = str(tmp_path / "test_export.json")
        export_snapshots(output_path, "2026-01-01")

        with open(output_path) as f:
            data = json.load(f)

        assert data["snapshot_date"] == "2026-01-01"
        assert "_instructions" in data
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["holdings"][0]["ticker"] == "AAPL"
