"""Tests for scripts/import_backfill_snapshot.py."""

import json
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from models import Account, AccountSnapshot, Holding, Security, SyncSession
from scripts.import_backfill_snapshot import (
    _parse_decimal,
    _resolve_security,
    import_snapshot,
)
from tests.fixtures import get_or_create_security


def _make_account(db: Session, name: str, provider: str = "SnapTrade", ext_id: str = "ext_1") -> Account:
    acct = Account(provider_name=provider, external_id=ext_id, name=name, is_active=True)
    db.add(acct)
    db.flush()
    return acct


def _write_json(tmp_path, data: dict) -> str:
    path = str(tmp_path / "backfill.json")
    with open(path, "w") as f:
        json.dump(data, f)
    return path


class TestParseDecimal:
    def test_none_returns_zero(self):
        assert _parse_decimal(None, "test") == Decimal("0")

    def test_string_value(self):
        assert _parse_decimal("150.50", "test") == Decimal("150.50")

    def test_int_value(self):
        assert _parse_decimal(10, "test") == Decimal("10")

    def test_float_value(self):
        assert _parse_decimal(10.5, "test") == Decimal("10.5")

    def test_invalid_value_exits(self):
        with pytest.raises(SystemExit):
            _parse_decimal("not_a_number", "test")


class TestResolveSecurity:
    def test_finds_by_security_id(self, db):
        sec = get_or_create_security(db, "AAPL", "Apple Inc.")
        result = _resolve_security(db, "AAPL", sec.id, None)
        assert result.id == sec.id

    def test_finds_by_ticker(self, db):
        sec = get_or_create_security(db, "AAPL", "Apple Inc.")
        result = _resolve_security(db, "AAPL", None, None)
        assert result.id == sec.id

    def test_creates_new_security(self, db):
        result = _resolve_security(db, "NEWT", None, "New Ticker Corp")
        assert result.ticker == "NEWT"
        assert result.name == "New Ticker Corp"
        assert result.id is not None

    def test_creates_with_ticker_as_name_when_no_name(self, db):
        result = _resolve_security(db, "NEWT", None, None)
        assert result.name == "NEWT"

    def test_security_id_not_found_falls_back_to_ticker(self, db):
        sec = get_or_create_security(db, "AAPL", "Apple Inc.")
        result = _resolve_security(db, "AAPL", "nonexistent-id", None)
        assert result.id == sec.id


class TestImportSnapshot:
    def test_missing_snapshot_date_exits(self, tmp_path):
        path = _write_json(tmp_path, {"accounts": []})
        with pytest.raises(SystemExit):
            import_snapshot(path)

    def test_invalid_date_format_exits(self, tmp_path):
        path = _write_json(tmp_path, {"snapshot_date": "not-a-date", "accounts": [{}]})
        with pytest.raises(SystemExit):
            import_snapshot(path)

    def test_empty_accounts_exits(self, tmp_path):
        path = _write_json(tmp_path, {"snapshot_date": "2026-01-01", "accounts": []})
        with pytest.raises(SystemExit):
            import_snapshot(path)

    def test_live_import_creates_records(self, db, tmp_path, monkeypatch):
        acct = _make_account(db, "Test Account", ext_id="e1")
        sec = get_or_create_security(db, "AAPL", "Apple Inc.")

        data = {
            "snapshot_date": "2026-01-01",
            "accounts": [{
                "account_id": acct.id,
                "account_name": "Test Account",
                "holdings": [{
                    "ticker": "AAPL",
                    "security_id": sec.id,
                    "quantity": "10",
                    "snapshot_price": "150.00",
                }],
            }],
        }
        path = _write_json(tmp_path, data)

        monkeypatch.setattr(
            "scripts.import_backfill_snapshot.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)

        import_snapshot(path, dry_run=False)

        # Verify SyncSession
        ss = db.query(SyncSession).filter(
            SyncSession.timestamp == datetime(2026, 1, 1, 12, 0, 0),
        ).first()
        assert ss is not None
        assert ss.is_complete is True

        # Verify AccountSnapshot
        snap = db.query(AccountSnapshot).filter(
            AccountSnapshot.sync_session_id == ss.id,
        ).first()
        assert snap is not None
        assert snap.account_id == acct.id
        assert snap.status == "success"
        assert snap.total_value == Decimal("1500.00")
        assert snap.balance_date is None

        # Verify Holding
        holding = db.query(Holding).filter(
            Holding.account_snapshot_id == snap.id,
        ).first()
        assert holding is not None
        assert holding.ticker == "AAPL"
        assert holding.quantity == Decimal("10")
        assert holding.snapshot_price == Decimal("150.00")
        assert holding.snapshot_value == Decimal("1500.00")

    def test_dry_run_does_not_persist(self, db, tmp_path, monkeypatch):
        acct = _make_account(db, "Test Account", ext_id="e1")
        get_or_create_security(db, "AAPL", "Apple Inc.")
        db.commit()

        data = {
            "snapshot_date": "2026-01-01",
            "accounts": [{
                "account_id": acct.id,
                "account_name": "Test Account",
                "holdings": [{
                    "ticker": "AAPL",
                    "quantity": "10",
                    "snapshot_price": "150.00",
                }],
            }],
        }
        path = _write_json(tmp_path, data)

        monkeypatch.setattr(
            "scripts.import_backfill_snapshot.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)

        import_snapshot(path, dry_run=True)

        # No SyncSession should persist after rollback
        count = db.query(SyncSession).filter(
            SyncSession.timestamp == datetime(2026, 1, 1, 12, 0, 0),
        ).count()
        assert count == 0

    def test_skips_missing_account_id(self, db, tmp_path, monkeypatch):
        data = {
            "snapshot_date": "2026-01-01",
            "accounts": [{
                "account_name": "No ID Account",
                "holdings": [{"ticker": "AAPL", "quantity": "10", "snapshot_price": "150"}],
            }],
        }
        path = _write_json(tmp_path, data)

        monkeypatch.setattr(
            "scripts.import_backfill_snapshot.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)

        import_snapshot(path, dry_run=False)

        # SyncSession exists but no AccountSnapshot
        ss = db.query(SyncSession).first()
        assert ss is not None
        snaps = db.query(AccountSnapshot).filter(
            AccountSnapshot.sync_session_id == ss.id,
        ).all()
        assert len(snaps) == 0

    def test_skips_nonexistent_account(self, db, tmp_path, monkeypatch):
        data = {
            "snapshot_date": "2026-01-01",
            "accounts": [{
                "account_id": "nonexistent-uuid",
                "account_name": "Ghost Account",
                "holdings": [{"ticker": "AAPL", "quantity": "10", "snapshot_price": "150"}],
            }],
        }
        path = _write_json(tmp_path, data)

        monkeypatch.setattr(
            "scripts.import_backfill_snapshot.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)

        import_snapshot(path, dry_run=False)

        snaps = db.query(AccountSnapshot).all()
        assert len(snaps) == 0

    def test_skips_holding_without_ticker(self, db, tmp_path, monkeypatch):
        acct = _make_account(db, "Test Account", ext_id="e1")

        data = {
            "snapshot_date": "2026-01-01",
            "accounts": [{
                "account_id": acct.id,
                "holdings": [
                    {"quantity": "10", "snapshot_price": "150"},  # no ticker
                    {"ticker": "AAPL", "quantity": "5", "snapshot_price": "150"},
                ],
            }],
        }
        path = _write_json(tmp_path, data)

        monkeypatch.setattr(
            "scripts.import_backfill_snapshot.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)

        import_snapshot(path, dry_run=False)

        holdings = db.query(Holding).all()
        assert len(holdings) == 1
        assert holdings[0].ticker == "AAPL"

    def test_creates_new_security_for_unknown_ticker(self, db, tmp_path, monkeypatch):
        acct = _make_account(db, "Test Account", ext_id="e1")

        data = {
            "snapshot_date": "2026-01-01",
            "accounts": [{
                "account_id": acct.id,
                "holdings": [{
                    "ticker": "NEWT",
                    "security_id": None,
                    "security_name": "New Ticker Corp",
                    "quantity": "100",
                    "snapshot_price": "25.00",
                }],
            }],
        }
        path = _write_json(tmp_path, data)

        monkeypatch.setattr(
            "scripts.import_backfill_snapshot.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)

        import_snapshot(path, dry_run=False)

        sec = db.query(Security).filter(Security.ticker == "NEWT").first()
        assert sec is not None
        assert sec.name == "New Ticker Corp"

    def test_recalculates_snapshot_value(self, db, tmp_path, monkeypatch):
        acct = _make_account(db, "Test Account", ext_id="e1")
        get_or_create_security(db, "AAPL")

        data = {
            "snapshot_date": "2026-01-01",
            "accounts": [{
                "account_id": acct.id,
                "holdings": [{
                    "ticker": "AAPL",
                    "quantity": "7.5",
                    "snapshot_price": "200.00",
                    "snapshot_value": "9999",  # should be ignored
                }],
            }],
        }
        path = _write_json(tmp_path, data)

        monkeypatch.setattr(
            "scripts.import_backfill_snapshot.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)

        import_snapshot(path, dry_run=False)

        holding = db.query(Holding).first()
        assert holding.snapshot_value == Decimal("1500.00")

    def test_duplicate_session_prompt_abort(self, db, tmp_path, monkeypatch):
        acct = _make_account(db, "Test Account", ext_id="e1")

        # Pre-create a session at the same timestamp
        existing_ss = SyncSession(
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            is_complete=True,
        )
        db.add(existing_ss)
        db.flush()

        data = {
            "snapshot_date": "2026-01-01",
            "accounts": [{
                "account_id": acct.id,
                "holdings": [{"ticker": "AAPL", "quantity": "10", "snapshot_price": "150"}],
            }],
        }
        path = _write_json(tmp_path, data)

        monkeypatch.setattr(
            "scripts.import_backfill_snapshot.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)
        monkeypatch.setattr("builtins.input", lambda _: "n")

        import_snapshot(path, dry_run=False)

        # Original session still exists, no new holdings created
        sessions = db.query(SyncSession).filter(
            SyncSession.timestamp == datetime(2026, 1, 1, 12, 0, 0),
        ).all()
        assert len(sessions) == 1
        assert sessions[0].id == existing_ss.id

    def test_duplicate_session_prompt_replace(self, db, tmp_path, monkeypatch):
        acct = _make_account(db, "Test Account", ext_id="e1")
        get_or_create_security(db, "AAPL")

        # Pre-create a session at the same timestamp
        existing_ss = SyncSession(
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            is_complete=True,
        )
        db.add(existing_ss)
        db.flush()
        old_id = existing_ss.id

        data = {
            "snapshot_date": "2026-01-01",
            "accounts": [{
                "account_id": acct.id,
                "holdings": [{"ticker": "AAPL", "quantity": "10", "snapshot_price": "150"}],
            }],
        }
        path = _write_json(tmp_path, data)

        monkeypatch.setattr(
            "scripts.import_backfill_snapshot.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)
        monkeypatch.setattr("builtins.input", lambda _: "y")

        import_snapshot(path, dry_run=False)

        # Old session deleted, new one created
        sessions = db.query(SyncSession).filter(
            SyncSession.timestamp == datetime(2026, 1, 1, 12, 0, 0),
        ).all()
        assert len(sessions) == 1
        assert sessions[0].id != old_id

        # New holdings exist
        holdings = db.query(Holding).all()
        assert len(holdings) == 1

    def test_multiple_accounts_multiple_holdings(self, db, tmp_path, monkeypatch):
        acct1 = _make_account(db, "Account One", ext_id="e1")
        acct2 = _make_account(db, "Account Two", provider="SimpleFIN", ext_id="e2")
        get_or_create_security(db, "AAPL")
        get_or_create_security(db, "GOOG")
        get_or_create_security(db, "MSFT")

        data = {
            "snapshot_date": "2026-01-01",
            "accounts": [
                {
                    "account_id": acct1.id,
                    "holdings": [
                        {"ticker": "AAPL", "quantity": "10", "snapshot_price": "150"},
                        {"ticker": "GOOG", "quantity": "5", "snapshot_price": "180"},
                    ],
                },
                {
                    "account_id": acct2.id,
                    "holdings": [
                        {"ticker": "MSFT", "quantity": "20", "snapshot_price": "400"},
                    ],
                },
            ],
        }
        path = _write_json(tmp_path, data)

        monkeypatch.setattr(
            "scripts.import_backfill_snapshot.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)

        import_snapshot(path, dry_run=False)

        snapshots = db.query(AccountSnapshot).all()
        assert len(snapshots) == 2

        holdings = db.query(Holding).all()
        assert len(holdings) == 3

        # Check total_values are computed correctly
        snap1 = db.query(AccountSnapshot).filter(
            AccountSnapshot.account_id == acct1.id,
        ).first()
        assert snap1.total_value == Decimal("2400")  # 10*150 + 5*180

        snap2 = db.query(AccountSnapshot).filter(
            AccountSnapshot.account_id == acct2.id,
        ).first()
        assert snap2.total_value == Decimal("8000")  # 20*400
