"""Tests for scripts/holdings_delta.py."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from models import Account, AccountSnapshot, DailyHoldingValue, SyncSession
from scripts.holdings_delta import _fmt_dec, _fmt_delta, _load_dhv
from tests.fixtures import get_or_create_security


def _make_account(db: Session, name: str, provider: str = "SnapTrade", ext_id: str = "ext_1") -> Account:
    acct = Account(provider_name=provider, external_id=ext_id, name=name, is_active=True)
    db.add(acct)
    db.flush()
    return acct


def _make_dhv(
    db: Session,
    account: Account,
    ticker: str,
    valuation_date: date,
    quantity: Decimal,
    close_price: Decimal,
) -> DailyHoldingValue:
    """Create a DailyHoldingValue row with a minimal snapshot chain."""
    sec = get_or_create_security(db, ticker, f"{ticker} Inc.")

    # Reuse or create a sync session + snapshot for this account
    snap = db.query(AccountSnapshot).filter(
        AccountSnapshot.account_id == account.id,
    ).first()
    if not snap:
        ss = SyncSession(timestamp=valuation_date, is_complete=True)
        db.add(ss)
        db.flush()
        snap = AccountSnapshot(
            account_id=account.id,
            sync_session_id=ss.id,
            status="success",
            total_value=Decimal("0"),
        )
        db.add(snap)
        db.flush()

    market_value = (quantity * close_price).quantize(Decimal("0.01"))
    dhv = DailyHoldingValue(
        valuation_date=valuation_date,
        account_id=account.id,
        account_snapshot_id=snap.id,
        security_id=sec.id,
        ticker=ticker,
        quantity=quantity,
        close_price=close_price,
        market_value=market_value,
    )
    db.add(dhv)
    db.flush()
    return dhv


class TestFmtDec:
    def test_basic(self):
        assert _fmt_dec(Decimal("1234.56")) == "1,234.56"

    def test_custom_places(self):
        assert _fmt_dec(Decimal("1234.5678"), 4) == "1,234.5678"

    def test_zero(self):
        assert _fmt_dec(Decimal("0")) == "0.00"


class TestFmtDelta:
    def test_positive(self):
        assert _fmt_delta(Decimal("100.50")) == "+100.50"

    def test_negative(self):
        assert _fmt_delta(Decimal("-50.25")) == "-50.25"

    def test_zero(self):
        assert _fmt_delta(Decimal("0")) == "0.00"


class TestLoadDhv:
    def test_empty_db(self, db):
        result = _load_dhv(db, date(2026, 1, 15), None)
        assert result == {}

    def test_loads_rows_for_date(self, db):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_dhv(db, acct, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))

        result = _load_dhv(db, date(2026, 1, 15), None)
        assert len(result) == 1
        key = (acct.id, list(result.values())[0].security_id)
        assert key in result
        assert result[key].ticker == "AAPL"

    def test_filters_by_account(self, db):
        acct1 = _make_account(db, "Account One", ext_id="e1")
        acct2 = _make_account(db, "Account Two", ext_id="e2")
        _make_dhv(db, acct1, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct2, "GOOG", date(2026, 1, 15), Decimal("5"), Decimal("180"))

        result = _load_dhv(db, date(2026, 1, 15), [acct1.id])
        assert len(result) == 1

    def test_ignores_other_dates(self, db):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_dhv(db, acct, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct, "GOOG", date(2026, 1, 16), Decimal("5"), Decimal("180"))

        result = _load_dhv(db, date(2026, 1, 15), None)
        assert len(result) == 1


class TestHoldingsDelta:
    """Integration tests for the full holdings_delta function."""

    def _run_delta(self, db, monkeypatch, capsys, date_a, date_b, account_filter=None, sort_by="value_delta"):
        monkeypatch.setattr(
            "scripts.holdings_delta.get_session_local",
            lambda: lambda: db,
        )
        monkeypatch.setattr(db, "close", lambda: None)

        from scripts.holdings_delta import holdings_delta
        holdings_delta(date_a, date_b, account_filter=account_filter, sort_by=sort_by)
        return capsys.readouterr().out

    def test_no_data_for_either_date(self, db, monkeypatch, capsys):
        output = self._run_delta(db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16))
        assert "No DHV data found" in output

    def test_price_change(self, db, monkeypatch, capsys):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_dhv(db, acct, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct, "AAPL", date(2026, 1, 16), Decimal("10"), Decimal("155"))

        output = self._run_delta(db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16))
        assert "PRICE" in output
        assert "AAPL" in output
        assert "+50.00" in output

    def test_quantity_change(self, db, monkeypatch, capsys):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_dhv(db, acct, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct, "AAPL", date(2026, 1, 16), Decimal("15"), Decimal("150"))

        output = self._run_delta(db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16))
        assert "QTY CHG" in output
        assert "+750.00" in output

    def test_holding_added(self, db, monkeypatch, capsys):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_dhv(db, acct, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct, "AAPL", date(2026, 1, 16), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct, "GOOG", date(2026, 1, 16), Decimal("5"), Decimal("180"))

        output = self._run_delta(db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16))
        assert "ADDED" in output
        assert "GOOG" in output

    def test_holding_removed(self, db, monkeypatch, capsys):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_dhv(db, acct, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct, "GOOG", date(2026, 1, 15), Decimal("5"), Decimal("180"))
        _make_dhv(db, acct, "AAPL", date(2026, 1, 16), Decimal("10"), Decimal("150"))

        output = self._run_delta(db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16))
        assert "REMOVED" in output
        assert "GOOG" in output

    def test_no_value_changes(self, db, monkeypatch, capsys):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_dhv(db, acct, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct, "AAPL", date(2026, 1, 16), Decimal("10"), Decimal("150"))

        output = self._run_delta(db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16))
        assert "No value changes" in output

    def test_account_filter_match(self, db, monkeypatch, capsys):
        acct1 = _make_account(db, "Vanguard Brokerage", ext_id="e1")
        acct2 = _make_account(db, "Schwab IRA", ext_id="e2")
        _make_dhv(db, acct1, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct1, "AAPL", date(2026, 1, 16), Decimal("10"), Decimal("155"))
        _make_dhv(db, acct2, "GOOG", date(2026, 1, 15), Decimal("5"), Decimal("180"))
        _make_dhv(db, acct2, "GOOG", date(2026, 1, 16), Decimal("5"), Decimal("190"))

        output = self._run_delta(
            db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16),
            account_filter="Vanguard",
        )
        assert "Filtering to 1 account(s)" in output
        assert "AAPL" in output
        assert "GOOG" not in output

    def test_account_filter_no_match(self, db, monkeypatch, capsys):
        output = self._run_delta(
            db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16),
            account_filter="Nonexistent",
        )
        assert "No accounts matching" in output

    def test_multi_account_summary(self, db, monkeypatch, capsys):
        acct1 = _make_account(db, "Account Alpha", ext_id="e1")
        acct2 = _make_account(db, "Account Beta", ext_id="e2")
        _make_dhv(db, acct1, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct1, "AAPL", date(2026, 1, 16), Decimal("10"), Decimal("155"))
        _make_dhv(db, acct2, "GOOG", date(2026, 1, 15), Decimal("5"), Decimal("180"))
        _make_dhv(db, acct2, "GOOG", date(2026, 1, 16), Decimal("5"), Decimal("190"))

        output = self._run_delta(db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16))
        assert "By account:" in output
        assert "Account Alpha" in output
        assert "Account Beta" in output

    def test_synthetic_ticker_shows_name(self, db, monkeypatch, capsys):
        acct = _make_account(db, "Test Account", ext_id="e1")
        # Use a synthetic ticker but give the security a recognizable name
        get_or_create_security(db, "_SF:x1", "My CD Fund")
        _make_dhv(db, acct, "_SF:x1", date(2026, 1, 15), Decimal("100"), Decimal("1"))
        _make_dhv(db, acct, "_SF:x1", date(2026, 1, 16), Decimal("100"), Decimal("1.10"))

        output = self._run_delta(db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16))
        # The detail table row should show security name, not the raw synthetic ticker
        detail_lines = [line for line in output.splitlines() if line.startswith("PRICE")]
        assert len(detail_lines) == 1
        assert "_SF:x1" not in detail_lines[0]
        assert "My CD Fund" in detail_lines[0]

    def test_sort_by_ticker(self, db, monkeypatch, capsys):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_dhv(db, acct, "GOOG", date(2026, 1, 15), Decimal("5"), Decimal("180"))
        _make_dhv(db, acct, "GOOG", date(2026, 1, 16), Decimal("5"), Decimal("190"))
        _make_dhv(db, acct, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct, "AAPL", date(2026, 1, 16), Decimal("10"), Decimal("155"))

        output = self._run_delta(
            db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16),
            sort_by="ticker",
        )
        # AAPL should appear before GOOG
        aapl_pos = output.index("AAPL")
        goog_pos = output.index("GOOG")
        assert aapl_pos < goog_pos

    def test_unchanged_holdings_count(self, db, monkeypatch, capsys):
        acct = _make_account(db, "Test Account", ext_id="e1")
        # AAPL changes price
        _make_dhv(db, acct, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct, "AAPL", date(2026, 1, 16), Decimal("10"), Decimal("155"))
        # GOOG stays the same
        _make_dhv(db, acct, "GOOG", date(2026, 1, 15), Decimal("5"), Decimal("180"))
        _make_dhv(db, acct, "GOOG", date(2026, 1, 16), Decimal("5"), Decimal("180"))

        output = self._run_delta(db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16))
        assert "(1 holdings unchanged)" in output

    def test_total_values_in_summary(self, db, monkeypatch, capsys):
        acct = _make_account(db, "Test Account", ext_id="e1")
        _make_dhv(db, acct, "AAPL", date(2026, 1, 15), Decimal("10"), Decimal("150"))
        _make_dhv(db, acct, "AAPL", date(2026, 1, 16), Decimal("10"), Decimal("160"))

        output = self._run_delta(db, monkeypatch, capsys, date(2026, 1, 15), date(2026, 1, 16))
        assert "$1,500.00" in output  # date_a total
        assert "$1,600.00" in output  # date_b total
        assert "+100.00" in output    # delta
