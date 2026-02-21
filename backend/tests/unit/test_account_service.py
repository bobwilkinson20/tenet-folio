"""Unit tests for AccountService.deactivate_account."""

from datetime import date, datetime, timezone
from decimal import Decimal

from models import Account, AccountSnapshot, DailyHoldingValue, Security, SyncSession
from services.account_service import AccountService
from utils.ticker import ZERO_BALANCE_TICKER


def _make_account(db, *, provider="SimpleFIN", external_id="ext_1", is_active=True):
    account = Account(
        provider_name=provider,
        external_id=external_id,
        name=f"Test {provider} Account",
        is_active=is_active,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _make_dhv(db, account_id, snapshot_id, ticker, valuation_date, market_value):
    """Create a DailyHoldingValue row (real holding, not sentinel)."""
    security = db.query(Security).filter_by(ticker=ticker).first()
    if not security:
        security = Security(ticker=ticker, name=ticker)
        db.add(security)
        db.flush()

    dhv = DailyHoldingValue(
        valuation_date=valuation_date,
        account_id=account_id,
        account_snapshot_id=snapshot_id,
        security_id=security.id,
        ticker=ticker,
        quantity=Decimal("1"),
        close_price=market_value,
        market_value=market_value,
    )
    db.add(dhv)
    db.commit()
    return dhv


def test_deactivate_sets_is_active_false(db):
    """Deactivating an account sets is_active=False."""
    account = _make_account(db)
    result = AccountService.deactivate_account(db, account.id, create_closing_snapshot=False)
    assert result is not None
    assert result.is_active is False


def test_deactivate_sets_deactivated_at(db):
    """Deactivating an account sets deactivated_at to approximately now."""
    account = _make_account(db)
    before = datetime.now(timezone.utc)
    result = AccountService.deactivate_account(db, account.id, create_closing_snapshot=False)
    after = datetime.now(timezone.utc)

    assert result.deactivated_at is not None
    # Compare naive datetimes (SQLite strips tzinfo)
    dt = result.deactivated_at.replace(tzinfo=timezone.utc) if result.deactivated_at.tzinfo is None else result.deactivated_at
    assert before <= dt <= after


def test_deactivate_returns_none_for_missing_account(db):
    """Deactivating a non-existent account returns None."""
    result = AccountService.deactivate_account(db, "nonexistent-id", create_closing_snapshot=False)
    assert result is None


def test_deactivate_already_inactive_is_noop(db):
    """Deactivating an already-inactive account is a no-op (returns account)."""
    account = _make_account(db, is_active=False)
    result = AccountService.deactivate_account(db, account.id, create_closing_snapshot=True)
    assert result is not None
    assert result.is_active is False
    # No new sync session or snapshot should have been created
    sessions = db.query(SyncSession).all()
    assert len(sessions) == 0


def test_deactivate_sets_superseded_by(db):
    """deactivate_account links the replacement account when provided."""
    old = _make_account(db, provider="SimpleFIN", external_id="sf_1")
    new = _make_account(db, provider="Plaid", external_id="plaid_1")

    result = AccountService.deactivate_account(
        db, old.id,
        create_closing_snapshot=False,
        superseded_by_account_id=new.id,
    )
    assert result.superseded_by_account_id == new.id


def test_deactivate_with_closing_snapshot_creates_sync_session(db):
    """When create_closing_snapshot=True, a new SyncSession is created."""
    account = _make_account(db)
    AccountService.deactivate_account(db, account.id, create_closing_snapshot=True)

    sessions = db.query(SyncSession).all()
    assert len(sessions) == 1
    assert sessions[0].is_complete is True


def test_deactivate_with_closing_snapshot_creates_account_snapshot(db):
    """Closing snapshot creates an AccountSnapshot with zero value and no holdings."""
    account = _make_account(db)
    AccountService.deactivate_account(db, account.id, create_closing_snapshot=True)

    snapshots = db.query(AccountSnapshot).filter_by(account_id=account.id).all()
    assert len(snapshots) == 1
    assert snapshots[0].total_value == Decimal("0")
    assert len(snapshots[0].holdings) == 0


def test_deactivate_with_closing_snapshot_writes_zero_balance_dhv(db):
    """Closing snapshot writes a _ZERO_BALANCE DHV row for today."""
    account = _make_account(db)
    AccountService.deactivate_account(db, account.id, create_closing_snapshot=True)

    sentinel_security = db.query(Security).filter_by(ticker=ZERO_BALANCE_TICKER).first()
    assert sentinel_security is not None

    dhv_rows = db.query(DailyHoldingValue).filter_by(account_id=account.id).all()
    assert len(dhv_rows) == 1
    assert dhv_rows[0].ticker == ZERO_BALANCE_TICKER
    assert dhv_rows[0].market_value == Decimal("0")
    assert dhv_rows[0].valuation_date == date.today()


def test_deactivate_with_closing_snapshot_skips_if_zero_already(db):
    """Closing snapshot is skipped if a zero-balance sentinel already exists for today."""
    account = _make_account(db)

    # Create a sync session and snapshot manually, write a zero sentinel
    session = SyncSession(timestamp=datetime.now(timezone.utc), is_complete=True)
    db.add(session)
    db.flush()
    snapshot = AccountSnapshot(
        account_id=account.id,
        sync_session_id=session.id,
        status="success",
        total_value=Decimal("0"),
    )
    db.add(snapshot)
    db.flush()

    from services.portfolio_valuation_service import PortfolioValuationService
    PortfolioValuationService.write_zero_balance_sentinel(
        db, account.id, snapshot.id, date.today()
    )
    db.commit()

    AccountService.deactivate_account(db, account.id, create_closing_snapshot=True)

    # Still only one sync session (the pre-existing one, not a new one)
    sessions = db.query(SyncSession).all()
    assert len(sessions) == 1

    # Still only one DHV row
    dhv_rows = db.query(DailyHoldingValue).filter_by(account_id=account.id).all()
    assert len(dhv_rows) == 1


def test_deactivate_no_closing_snapshot_skips_session(db):
    """When create_closing_snapshot=False, no SyncSession or DHV is created."""
    account = _make_account(db)
    AccountService.deactivate_account(db, account.id, create_closing_snapshot=False)

    assert db.query(SyncSession).count() == 0
    assert db.query(DailyHoldingValue).count() == 0
