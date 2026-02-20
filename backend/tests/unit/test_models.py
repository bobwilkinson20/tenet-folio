"""Unit tests for SQLAlchemy models."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models import HoldingLot, LotDisposal
from models.sync_log import SyncLogEntry


def test_asset_class_creation(asset_class):
    """Test AssetClass model creation."""
    assert asset_class.name == "Test Asset Class"
    assert asset_class.target_percent == Decimal("50.00")
    assert asset_class.created_at is not None
    assert asset_class.updated_at is not None


def test_account_creation(account):
    """Test Account model creation."""
    assert account.provider_name == "SnapTrade"
    assert account.external_id == "ext_123"
    assert account.name == "Test Account"
    assert account.is_active is True
    assert account.created_at is not None


def test_account_with_asset_class(account, asset_class):
    """Test Account relationship with AssetClass."""
    assert account.assigned_asset_class_id == asset_class.id
    assert account.assigned_asset_class.name == "Test Asset Class"


def test_security_creation(security):
    """Test Security model creation."""
    assert security.ticker == "AAPL"
    assert security.name == "Apple Inc."
    assert security.created_at is not None


def test_sync_session_creation(sync_session):
    """Test SyncSession model creation."""
    assert sync_session.timestamp is not None
    assert sync_session.is_complete is True
    assert sync_session.error_message is None


def test_holding_creation(holding):
    """Test Holding model creation."""
    assert holding.ticker == "AAPL"
    assert holding.quantity == Decimal("10.00")
    assert holding.snapshot_price == Decimal("150.50")
    assert holding.snapshot_value == Decimal("1505.00")


def test_holding_relationships(holding, account_snapshot):
    """Test Holding relationship with AccountSnapshot."""
    assert holding.account_snapshot_id == account_snapshot.id
    assert holding.account_snapshot.account.name == "Test Account"


def test_sync_log_entry_creation(db, sync_session):
    """Test SyncLogEntry model creation."""
    entry = SyncLogEntry(
        sync_session_id=sync_session.id,
        provider_name="SimpleFIN",
        status="success",
        accounts_synced=3,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    assert entry.id is not None
    assert entry.provider_name == "SimpleFIN"
    assert entry.status == "success"
    assert entry.error_messages is None
    assert entry.accounts_synced == 3
    assert entry.created_at is not None


def test_sync_log_entry_with_errors(db, sync_session):
    """Test SyncLogEntry with error messages."""
    entry = SyncLogEntry(
        sync_session_id=sync_session.id,
        provider_name="SnapTrade",
        status="failed",
        error_messages=["API rate limit exceeded", "Connection timeout"],
        accounts_synced=0,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    assert entry.status == "failed"
    assert entry.error_messages == ["API rate limit exceeded", "Connection timeout"]
    assert entry.accounts_synced == 0


def test_sync_session_sync_log_entries_relationship(db, sync_session):
    """Test SyncSession.sync_log_entries relationship."""
    entry1 = SyncLogEntry(
        sync_session_id=sync_session.id,
        provider_name="SnapTrade",
        status="success",
        accounts_synced=2,
    )
    entry2 = SyncLogEntry(
        sync_session_id=sync_session.id,
        provider_name="SimpleFIN",
        status="partial",
        error_messages=["Connection timeout for 1 account"],
        accounts_synced=1,
    )
    db.add_all([entry1, entry2])
    db.commit()
    db.refresh(sync_session)

    assert len(sync_session.sync_log_entries) == 2
    provider_names = {e.provider_name for e in sync_session.sync_log_entries}
    assert provider_names == {"SnapTrade", "SimpleFIN"}


def test_sync_log_entry_accounts_stale(db, sync_session):
    """Test SyncLogEntry.accounts_stale field."""
    entry = SyncLogEntry(
        sync_session_id=sync_session.id,
        provider_name="SimpleFIN",
        status="success",
        accounts_synced=1,
        accounts_stale=2,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    assert entry.accounts_stale == 2


def test_account_balance_date(db, account):
    """Test Account.balance_date field."""
    assert account.balance_date is None

    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)
    account.balance_date = bd
    db.commit()
    db.refresh(account)

    assert account.balance_date is not None


# --- HoldingLot model tests ---


def test_holding_lot_creation(holding_lot):
    """Test HoldingLot model creation with all fields."""
    assert holding_lot.id is not None
    assert holding_lot.ticker == "AAPL"
    assert holding_lot.acquisition_date == date(2025, 1, 15)
    assert holding_lot.cost_basis_per_unit == Decimal("150.50")
    assert holding_lot.original_quantity == Decimal("10.00")
    assert holding_lot.current_quantity == Decimal("10.00")
    assert holding_lot.is_closed is False
    assert holding_lot.source == "activity"
    assert holding_lot.created_at is not None
    assert holding_lot.updated_at is not None


def test_holding_lot_relationships(holding_lot, account, security, activity):
    """Test HoldingLot relationships to Account, Security, Activity."""
    assert holding_lot.account_id == account.id
    assert holding_lot.account.name == "Test Account"
    assert holding_lot.security_id == security.id
    assert holding_lot.security.ticker == "AAPL"
    assert holding_lot.activity_id == activity.id
    assert holding_lot.activity.type == "buy"


def test_holding_lot_back_populates(holding_lot, account, security):
    """Test back_populates from Account and Security to HoldingLot."""
    assert holding_lot in account.holding_lots
    assert holding_lot in security.holding_lots


def test_holding_lot_nullable_acquisition_date(db, account, security):
    """Test HoldingLot with null acquisition_date (inferred lots)."""
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        acquisition_date=None,
        cost_basis_per_unit=Decimal("100.00"),
        original_quantity=Decimal("5.00"),
        current_quantity=Decimal("5.00"),
        source="inferred",
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    assert lot.acquisition_date is None


def test_holding_lot_nullable_activity(db, account, security):
    """Test HoldingLot without an activity link."""
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        cost_basis_per_unit=Decimal("0"),
        original_quantity=Decimal("1.00"),
        current_quantity=Decimal("1.00"),
        source="manual",
        activity_id=None,
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    assert lot.activity_id is None
    assert lot.activity is None


def test_holding_lot_cost_basis_default(db, account, security):
    """Test cost_basis_per_unit defaults to 0."""
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        original_quantity=Decimal("1.00"),
        current_quantity=Decimal("1.00"),
        source="initial",
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    assert lot.cost_basis_per_unit == Decimal("0")


def test_holding_lot_check_constraint_negative_cost_basis(db, account, security):
    """Test CheckConstraint rejects negative cost_basis_per_unit."""
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        cost_basis_per_unit=Decimal("-1.00"),
        original_quantity=Decimal("1.00"),
        current_quantity=Decimal("1.00"),
        source="manual",
    )
    db.add(lot)
    with pytest.raises(IntegrityError):
        db.commit()


def test_holding_lot_check_constraint_zero_original_quantity(db, account, security):
    """Test CheckConstraint rejects zero original_quantity."""
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        cost_basis_per_unit=Decimal("100.00"),
        original_quantity=Decimal("0"),
        current_quantity=Decimal("0"),
        source="manual",
    )
    db.add(lot)
    with pytest.raises(IntegrityError):
        db.commit()


def test_holding_lot_check_constraint_negative_current_quantity(db, account, security):
    """Test CheckConstraint rejects negative current_quantity."""
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        cost_basis_per_unit=Decimal("100.00"),
        original_quantity=Decimal("10.00"),
        current_quantity=Decimal("-1.00"),
        source="manual",
    )
    db.add(lot)
    with pytest.raises(IntegrityError):
        db.commit()


def test_holding_lot_allows_zero_current_quantity(db, account, security):
    """Test that current_quantity=0 is allowed (fully disposed lot)."""
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        cost_basis_per_unit=Decimal("100.00"),
        original_quantity=Decimal("10.00"),
        current_quantity=Decimal("0"),
        is_closed=True,
        source="activity",
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    assert lot.current_quantity == Decimal("0")
    assert lot.is_closed is True


# --- LotDisposal model tests ---


def test_lot_disposal_creation(lot_disposal):
    """Test LotDisposal model creation with all fields."""
    assert lot_disposal.id is not None
    assert lot_disposal.disposal_date == date(2025, 6, 15)
    assert lot_disposal.quantity == Decimal("3.00")
    assert lot_disposal.proceeds_per_unit == Decimal("175.25")
    assert lot_disposal.source == "activity"
    assert lot_disposal.disposal_group_id == "group_001"
    assert lot_disposal.created_at is not None
    assert lot_disposal.updated_at is not None


def test_lot_disposal_relationships(lot_disposal, holding_lot, account, security):
    """Test LotDisposal relationships."""
    assert lot_disposal.holding_lot_id == holding_lot.id
    assert lot_disposal.holding_lot.ticker == "AAPL"
    assert lot_disposal.account_id == account.id
    assert lot_disposal.account.name == "Test Account"
    assert lot_disposal.security_id == security.id
    assert lot_disposal.security.ticker == "AAPL"


def test_lot_disposal_back_populates_holding_lot(lot_disposal, holding_lot):
    """Test HoldingLot.disposals back_populates from LotDisposal."""
    assert lot_disposal in holding_lot.disposals


def test_lot_disposal_cascade_delete(db, holding_lot, lot_disposal):
    """Test that deleting a HoldingLot cascades to its disposals."""
    disposal_id = lot_disposal.id
    db.delete(holding_lot)
    db.commit()
    assert db.get(LotDisposal, disposal_id) is None


def test_lot_disposal_nullable_activity(db, holding_lot, account, security):
    """Test LotDisposal without an activity link."""
    disposal = LotDisposal(
        holding_lot_id=holding_lot.id,
        account_id=account.id,
        security_id=security.id,
        disposal_date=date(2025, 7, 1),
        quantity=Decimal("1.00"),
        proceeds_per_unit=Decimal("200.00"),
        source="manual",
        activity_id=None,
        disposal_group_id=None,
    )
    db.add(disposal)
    db.commit()
    db.refresh(disposal)
    assert disposal.activity_id is None
    assert disposal.disposal_group_id is None


def test_lot_disposal_proceeds_default(db, holding_lot, account, security):
    """Test proceeds_per_unit defaults to 0."""
    disposal = LotDisposal(
        holding_lot_id=holding_lot.id,
        account_id=account.id,
        security_id=security.id,
        disposal_date=date(2025, 7, 1),
        quantity=Decimal("1.00"),
        source="inferred",
    )
    db.add(disposal)
    db.commit()
    db.refresh(disposal)
    assert disposal.proceeds_per_unit == Decimal("0")


def test_lot_disposal_check_constraint_zero_quantity(db, holding_lot, account, security):
    """Test CheckConstraint rejects zero disposal quantity."""
    disposal = LotDisposal(
        holding_lot_id=holding_lot.id,
        account_id=account.id,
        security_id=security.id,
        disposal_date=date(2025, 7, 1),
        quantity=Decimal("0"),
        proceeds_per_unit=Decimal("100.00"),
        source="manual",
    )
    db.add(disposal)
    with pytest.raises(IntegrityError):
        db.commit()


def test_lot_disposal_check_constraint_negative_proceeds(db, holding_lot, account, security):
    """Test CheckConstraint rejects negative proceeds_per_unit."""
    disposal = LotDisposal(
        holding_lot_id=holding_lot.id,
        account_id=account.id,
        security_id=security.id,
        disposal_date=date(2025, 7, 1),
        quantity=Decimal("1.00"),
        proceeds_per_unit=Decimal("-5.00"),
        source="manual",
    )
    db.add(disposal)
    with pytest.raises(IntegrityError):
        db.commit()
