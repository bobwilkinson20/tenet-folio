"""Test fixtures and sample data."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from models import Account, AccountSnapshot, AssetClass, DailyHoldingValue, HoldingLot, LotDisposal, Security, SyncSession, Holding
from models.activity import Activity
from models.sync_log import SyncLogEntry
from sqlalchemy.orm import Session


def create_sync_session_with_holdings(
    db: Session,
    account: Account,
    ts: datetime,
    holdings_data: list[tuple[str, Decimal]],
    total_value: Decimal | None = None,
) -> SyncSession:
    """Create a sync session with holdings and DailyHoldingValues for an account.

    Args:
        db: Database session
        account: Account to create holdings for
        ts: Timestamp for the sync session; ts.date() is used as the DHV valuation_date
        holdings_data: List of (ticker, market_value) tuples
        total_value: Optional override for AccountSnapshot.total_value
                     (defaults to sum of market_values)

    Returns:
        The created SyncSession
    """
    snap = SyncSession(timestamp=ts, is_complete=True)
    db.add(snap)
    db.flush()

    computed_total = sum(mv for _, mv in holdings_data)

    acct_snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=snap.id,
        status="success",
        total_value=total_value if total_value is not None else computed_total,
    )
    db.add(acct_snap)
    db.flush()

    val_date = ts.date()
    for ticker, market_value in holdings_data:
        security = get_or_create_security(db, ticker)
        db.add(
            Holding(
                account_snapshot_id=acct_snap.id,
                security_id=security.id,
                ticker=ticker,
                quantity=Decimal("1"),
                snapshot_price=market_value,
                snapshot_value=market_value,
            )
        )
        db.add(
            DailyHoldingValue(
                valuation_date=val_date,
                account_id=account.id,
                account_snapshot_id=acct_snap.id,
                security_id=security.id,
                ticker=ticker,
                quantity=Decimal("1"),
                close_price=market_value,
                market_value=market_value,
            )
        )

    db.flush()
    return snap


def get_or_create_security(db: Session, ticker: str, name: str | None = None) -> Security:
    """Get or create a Security record for the given ticker.

    This is a helper function (not a fixture) for tests that need to create
    multiple securities with different tickers.
    """
    security = db.query(Security).filter_by(ticker=ticker).first()
    if not security:
        security = Security(ticker=ticker, name=name or ticker)
        db.add(security)
        db.flush()
    return security


@pytest.fixture
def asset_class(db: Session) -> AssetClass:
    """Create a test asset class."""
    ac = AssetClass(
        name="Test Asset Class",
        target_percent=Decimal("50.00"),
    )
    db.add(ac)
    db.commit()
    db.refresh(ac)
    return ac


@pytest.fixture
def account(db: Session, asset_class: AssetClass) -> Account:
    """Create a test account."""
    acc = Account(
        provider_name="SnapTrade",
        external_id="ext_123",
        name="Test Account",
        institution_name="Test Brokerage",
        is_active=True,
        assigned_asset_class_id=asset_class.id,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


@pytest.fixture
def account_without_asset_class(db: Session) -> Account:
    """Create a test account without an asset class."""
    acc = Account(
        provider_name="SnapTrade",
        external_id="ext_456",
        name="Another Account",
        is_active=True,
        assigned_asset_class_id=None,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


@pytest.fixture
def security(db: Session, asset_class: AssetClass) -> Security:
    """Create a test security."""
    sec = Security(
        ticker="AAPL",
        name="Apple Inc.",
        manual_asset_class_id=asset_class.id,
    )
    db.add(sec)
    db.commit()
    db.refresh(sec)
    return sec


@pytest.fixture
def sync_session(db: Session) -> SyncSession:
    """Create a test sync session."""
    ss = SyncSession(
        timestamp=datetime.now(timezone.utc),
        is_complete=True,
    )
    db.add(ss)
    db.commit()
    db.refresh(ss)
    return ss


@pytest.fixture
def holding(db: Session, account_snapshot: AccountSnapshot, security: Security) -> Holding:
    """Create a test holding linked to an account snapshot."""
    hold = Holding(
        account_snapshot_id=account_snapshot.id,
        security_id=security.id,
        ticker="AAPL",
        quantity=Decimal("10.00"),
        snapshot_price=Decimal("150.50"),
        snapshot_value=Decimal("1505.00"),
    )
    db.add(hold)
    db.commit()
    db.refresh(hold)
    return hold


@pytest.fixture
def sync_log_entry(db: Session, sync_session: SyncSession) -> SyncLogEntry:
    """Create a test sync log entry."""
    entry = SyncLogEntry(
        sync_session_id=sync_session.id,
        provider_name="SnapTrade",
        status="success",
        accounts_synced=2,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@pytest.fixture
def account_snapshot(db: Session, sync_session: SyncSession, account: Account) -> AccountSnapshot:
    """Create a test account snapshot."""
    acct_snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=sync_session.id,
        status="success",
        total_value=Decimal("1505.00"),
    )
    db.add(acct_snap)
    db.commit()
    db.refresh(acct_snap)
    return acct_snap


@pytest.fixture
def activity(db: Session, account: Account) -> Activity:
    """Create a test activity."""
    act = Activity(
        account_id=account.id,
        provider_name="SnapTrade",
        external_id="act_001",
        activity_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
        type="buy",
        description="Bought AAPL",
        ticker="AAPL",
        units=Decimal("10.00"),
        price=Decimal("150.50"),
        amount=Decimal("1505.00"),
        currency="USD",
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


@pytest.fixture
def holding_lot(db: Session, account: Account, security: Security, activity: Activity) -> HoldingLot:
    """Create a test holding lot."""
    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        acquisition_date=datetime(2025, 1, 15, tzinfo=timezone.utc).date(),
        cost_basis_per_unit=Decimal("150.50"),
        original_quantity=Decimal("10.00"),
        current_quantity=Decimal("10.00"),
        is_closed=False,
        source="activity",
        activity_id=activity.id,
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


@pytest.fixture
def lot_disposal(db: Session, holding_lot: HoldingLot, account: Account, security: Security) -> LotDisposal:
    """Create a test lot disposal."""
    disposal = LotDisposal(
        holding_lot_id=holding_lot.id,
        account_id=account.id,
        security_id=security.id,
        disposal_date=datetime(2025, 6, 15, tzinfo=timezone.utc).date(),
        quantity=Decimal("3.00"),
        proceeds_per_unit=Decimal("175.25"),
        source="activity",
        disposal_group_id="group_001",
    )
    db.add(disposal)
    db.commit()
    db.refresh(disposal)
    return disposal
