"""Unit tests for SyncService."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from integrations.provider_protocol import ErrorCategory, ProviderSyncError
from models import Account, AccountSnapshot, DailyHoldingValue, Holding, Security
from models.activity import Activity
from models.sync_log import SyncLogEntry
from schemas import ManualHoldingInput
from services.manual_holdings_service import ManualHoldingsService
from services.sync_service import SyncService
from tests.fixtures.mocks import (
    MockCoinbaseClient,
    MockIBKRFlexClient,
    MockProviderRegistry,
    MockSchwabClient,
    MockSimpleFINClient,
    MockSnapTradeClient,
    SAMPLE_COINBASE_ACCOUNTS,
    SAMPLE_COINBASE_ACTIVITIES,
    SAMPLE_COINBASE_HOLDINGS,
    SAMPLE_IBKR_ACCOUNTS,
    SAMPLE_IBKR_ACTIVITIES,
    SAMPLE_IBKR_HOLDINGS,
    SAMPLE_SCHWAB_ACCOUNTS,
    SAMPLE_SCHWAB_ACTIVITIES,
    SAMPLE_SCHWAB_HOLDINGS,
    SAMPLE_SIMPLEFIN_ACCOUNTS,
    SAMPLE_SNAPTRADE_ACCOUNTS,
    SAMPLE_SNAPTRADE_HOLDINGS,
)


def _create_accounts(db, provider_name, external_ids):
    """Helper to create test accounts (for tests needing pre-existing accounts)."""
    accounts = []
    for ext_id in external_ids:
        acc = Account(
            provider_name=provider_name,
            external_id=ext_id,
            name=f"Account {ext_id}",
            is_active=True,
        )
        db.add(acc)
        accounts.append(acc)
    db.commit()
    return accounts


def test_sync_creates_log_entries(db):
    """Sync creates SyncLogEntry records for each provider."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 1
    assert entries[0].provider_name == "SnapTrade"
    assert entries[0].status == "success"
    assert entries[0].accounts_synced == 2


def test_sync_upserts_accounts(db):
    """Unified sync creates Account records from provider data."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    accounts = db.query(Account).all()
    assert len(accounts) == 2
    assert {a.external_id for a in accounts} == {"st_acc_001", "st_acc_002"}
    assert {a.provider_name for a in accounts} == {"SnapTrade"}
    assert all(a.is_active for a in accounts)


def test_sync_upserts_accounts_idempotent(db):
    """Syncing twice does not duplicate accounts."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)
    service.trigger_sync(db)

    accounts = db.query(Account).all()
    assert len(accounts) == 2


def test_sync_preserves_user_edited_names(db):
    """Sync does not overwrite user-edited account names."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    # First sync creates accounts
    service.trigger_sync(db)

    # User edits account name
    account = db.query(Account).filter_by(external_id="st_acc_001").first()
    account.name = "My Custom Name"
    account.name_user_edited = True
    db.commit()

    # Second sync should preserve user-edited name
    service.trigger_sync(db)

    db.refresh(account)
    assert account.name == "My Custom Name"


def test_sync_captures_provider_errors_in_log(db):
    """Provider-reported errors are captured in sync log entries."""
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS,
        errors=["Connection timeout for institution XYZ"],
        balance_dates={"sf_acc_001": datetime(2026, 1, 28, tzinfo=timezone.utc)},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.provider_name == "SimpleFIN"
    assert entry.status == "partial"  # errors + some success
    assert any("Connection timeout" in msg for msg in entry.error_messages)


def test_sync_stores_balance_date_on_account(db):
    """Balance dates from provider are stored on Account model."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS,
        balance_dates={
            "sf_acc_001": bd,
            "sf_acc_002": None,
        },
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    acc1 = db.query(Account).filter_by(external_id="sf_acc_001").first()
    acc2 = db.query(Account).filter_by(external_id="sf_acc_002").first()

    assert acc1.balance_date is not None
    assert acc2.balance_date is None


def test_failed_provider_creates_failed_log_entry(db):
    """A provider that raises an exception creates a failed log entry."""
    mock_st = MockSnapTradeClient(
        should_fail=True,
        failure_message="SnapTrade API unavailable",
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    # Pre-create an account so it gets marked as failed
    _create_accounts(db, "SnapTrade", ["st_acc_001"])

    sync_session = service.trigger_sync(db)

    assert sync_session.is_complete is False
    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 1
    assert entries[0].status == "failed"
    assert "SnapTrade API unavailable" in entries[0].error_messages[0]
    assert entries[0].accounts_synced == 0


def test_multi_provider_creates_multiple_log_entries(db):
    """Syncing multiple providers creates a log entry for each."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS,
    )
    registry = MockProviderRegistry({
        "SnapTrade": mock_st,
        "SimpleFIN": mock_sf,
    })
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 2
    provider_names = {e.provider_name for e in entries}
    assert provider_names == {"SnapTrade", "SimpleFIN"}


def test_partial_failure_one_provider_fails(db):
    """When one provider fails and another succeeds, sync_session is still complete."""
    mock_st = MockSnapTradeClient(
        should_fail=True,
        failure_message="SnapTrade down",
    )
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS,
    )
    registry = MockProviderRegistry({
        "SnapTrade": mock_st,
        "SimpleFIN": mock_sf,
    })
    service = SyncService(provider_registry=registry)

    # Pre-create SnapTrade account so it gets marked as failed
    _create_accounts(db, "SnapTrade", ["st_acc_001"])

    sync_session = service.trigger_sync(db)

    # SimpleFIN succeeded, so sync_session should be complete
    assert sync_session.is_complete is True

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 2
    entry_map = {e.provider_name: e for e in entries}
    assert entry_map["SnapTrade"].status == "failed"
    assert entry_map["SimpleFIN"].status == "success"


def test_sync_creates_account_snapshots(db):
    """Sync creates AccountSnapshot records for each synced account."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    acct_snaps = db.query(AccountSnapshot).filter_by(sync_session_id=sync_session.id).all()
    assert len(acct_snaps) == 2
    assert all(s.status == "success" for s in acct_snaps)


def test_sync_account_snapshot_records_total_value(db):
    """AccountSnapshot total_value matches sum of holdings market_value."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    acct_snaps = db.query(AccountSnapshot).filter_by(sync_session_id=sync_session.id).all()
    snap_map = {s.account_id: s for s in acct_snaps}

    # Account st_acc_001: AAPL 15050 + GOOGL 7012.50 = 22062.50
    acc1 = db.query(Account).filter_by(external_id="st_acc_001").first()
    assert Decimal(str(snap_map[acc1.id].total_value)) == Decimal("22062.50")

    # Account st_acc_002: VTI 44000
    acc2 = db.query(Account).filter_by(external_id="st_acc_002").first()
    assert Decimal(str(snap_map[acc2.id].total_value)) == Decimal("44000.00")


def test_sync_empty_holdings_creates_zero_value_account_snapshot(db):
    """Liquidated account (no holdings) gets AccountSnapshot with total_value=0."""
    # Provider returns accounts but no holdings (fully liquidated)
    from integrations.snaptrade_client import SnapTradeAccount

    liquidated_accounts = [
        SnapTradeAccount(
            id="liq_001",
            name="Liquidated Account",
            brokerage_name="TestBroker",
            account_number="LIQ001",
        ),
    ]
    mock_st = MockSnapTradeClient(
        accounts=liquidated_accounts,
        holdings=[],  # No holdings - account is fully liquidated
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    acct_snaps = db.query(AccountSnapshot).filter_by(sync_session_id=sync_session.id).all()
    assert len(acct_snaps) == 1
    assert acct_snaps[0].status == "success"
    assert Decimal(str(acct_snaps[0].total_value)) == Decimal("0")


# --- IBKR sync pipeline tests ---


def test_ibkr_sync_creates_accounts(db):
    """IBKR sync creates Account records with provider_name='IBKR'."""
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    accounts = db.query(Account).filter_by(provider_name="IBKR").all()
    assert len(accounts) == 2
    assert {a.external_id for a in accounts} == {"ib_acc_001", "ib_acc_002"}
    assert all(a.is_active for a in accounts)
    assert all(a.institution_name == "Interactive Brokers" for a in accounts)


def test_ibkr_sync_creates_holdings_with_cash(db):
    """IBKR sync creates holdings including synthetic _CASH:USD entries."""
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    holdings = db.query(Holding).join(AccountSnapshot).filter(AccountSnapshot.sync_session_id == sync_session.id).all()
    # 5 total: AAPL, MSFT, _CASH:USD (acc_001) + VTI, _CASH:USD (acc_002)
    assert len(holdings) == 5

    tickers = {h.ticker for h in holdings}
    assert "AAPL" in tickers
    assert "MSFT" in tickers
    assert "VTI" in tickers
    assert "_CASH:USD" in tickers

    # Verify cash holdings have correct values
    cash_holdings = [h for h in holdings if h.ticker == "_CASH:USD"]
    assert len(cash_holdings) == 2
    cash_values = sorted([h.snapshot_value for h in cash_holdings])
    assert cash_values == [Decimal("1000.00"), Decimal("5432.10")]


def test_ibkr_sync_creates_log_entry(db):
    """IBKR sync creates a SyncLogEntry with provider_name='IBKR' and status='success'."""
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 1
    assert entries[0].provider_name == "IBKR"
    assert entries[0].status == "success"
    assert entries[0].accounts_synced == 2


def test_ibkr_sync_activities_stored(db):
    """IBKR activities are persisted and retrievable by account."""
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
        activities=SAMPLE_IBKR_ACTIVITIES,
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    account = db.query(Account).filter_by(external_id="ib_acc_001").first()
    activities = (
        db.query(Activity)
        .filter_by(account_id=account.id, provider_name="IBKR")
        .all()
    )
    assert len(activities) == 5
    ext_ids = {a.external_id for a in activities}
    assert ext_ids == {"T001", "T002", "CT:CT001", "CT:CT002", "CT:CT003"}

    buy = next(a for a in activities if a.external_id == "T001")
    assert buy.type == "buy"
    assert buy.ticker == "AAPL"

    sell = next(a for a in activities if a.external_id == "T002")
    assert sell.type == "sell"
    assert sell.ticker == "GOOGL"

    dividend = next(a for a in activities if a.external_id == "CT:CT001")
    assert dividend.type == "dividend"
    assert dividend.ticker == "AAPL"

    deposit = next(a for a in activities if a.external_id == "CT:CT002")
    assert deposit.type == "deposit"

    interest = next(a for a in activities if a.external_id == "CT:CT003")
    assert interest.type == "interest"


def test_ibkr_sync_balance_dates_stored(db):
    """Balance dates from IBKR provider are stored on Account.balance_date."""
    bd = datetime(2026, 1, 28, 18, 0, 0, tzinfo=timezone.utc)
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
        balance_dates={
            "ib_acc_001": bd,
            "ib_acc_002": None,
        },
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    acc1 = db.query(Account).filter_by(external_id="ib_acc_001").first()
    acc2 = db.query(Account).filter_by(external_id="ib_acc_002").first()

    assert acc1.balance_date is not None
    assert acc2.balance_date is None


def test_ibkr_alongside_other_providers(db):
    """Three-provider sync (SnapTrade + SimpleFIN + IBKR) creates separate log entries."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS,
    )
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
    )
    registry = MockProviderRegistry({
        "SnapTrade": mock_st,
        "SimpleFIN": mock_sf,
        "IBKR": mock_ibkr,
    })
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 3
    provider_names = {e.provider_name for e in entries}
    assert provider_names == {"SnapTrade", "SimpleFIN", "IBKR"}

    # Accounts are scoped by provider
    st_accounts = db.query(Account).filter_by(provider_name="SnapTrade").all()
    sf_accounts = db.query(Account).filter_by(provider_name="SimpleFIN").all()
    ib_accounts = db.query(Account).filter_by(provider_name="IBKR").all()
    assert len(st_accounts) == 2
    assert len(sf_accounts) == 3
    assert len(ib_accounts) == 2


def test_ibkr_sync_account_upsert_idempotent(db):
    """Syncing IBKR twice does not duplicate accounts."""
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)
    service.trigger_sync(db)

    accounts = db.query(Account).filter_by(provider_name="IBKR").all()
    assert len(accounts) == 2


def test_ibkr_failure_doesnt_block_other_providers(db):
    """IBKR failure + SimpleFIN success → sync_session.is_complete=True, IBKR log='failed'."""
    mock_ibkr = MockIBKRFlexClient(should_fail=True)
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS,
    )
    registry = MockProviderRegistry({
        "IBKR": mock_ibkr,
        "SimpleFIN": mock_sf,
    })
    service = SyncService(provider_registry=registry)

    # Pre-create an IBKR account so it gets marked as failed
    _create_accounts(db, "IBKR", ["ib_acc_001"])

    sync_session = service.trigger_sync(db)

    # SimpleFIN succeeded, so sync_session should be complete
    assert sync_session.is_complete is True

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 2
    entry_map = {e.provider_name: e for e in entries}
    assert entry_map["IBKR"].status == "failed"
    assert entry_map["SimpleFIN"].status == "success"


# --- Coinbase sync pipeline tests ---


def test_coinbase_sync_creates_accounts(db):
    """Coinbase sync creates Account records with provider_name='Coinbase'."""
    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=SAMPLE_COINBASE_HOLDINGS,
    )
    registry = MockProviderRegistry({"Coinbase": mock_cb})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    accounts = db.query(Account).filter_by(provider_name="Coinbase").all()
    assert len(accounts) == 1
    assert accounts[0].external_id == "cb_port_001"
    assert accounts[0].name == "Default Portfolio"
    assert accounts[0].institution_name == "Coinbase"
    assert accounts[0].is_active


def test_coinbase_sync_creates_holdings_with_cash(db):
    """Coinbase sync creates holdings including crypto and _CASH:USD entries."""
    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=SAMPLE_COINBASE_HOLDINGS,
    )
    registry = MockProviderRegistry({"Coinbase": mock_cb})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    holdings = db.query(Holding).join(AccountSnapshot).filter(AccountSnapshot.sync_session_id == sync_session.id).all()
    assert len(holdings) == 3

    tickers = {h.ticker for h in holdings}
    assert "BTC" in tickers
    assert "ETH" in tickers
    assert "_CASH:USD" in tickers

    cash = next(h for h in holdings if h.ticker == "_CASH:USD")
    assert cash.snapshot_value == Decimal("2500")


def test_coinbase_sync_creates_log_entry(db):
    """Coinbase sync creates a SyncLogEntry with provider_name='Coinbase' and status='success'."""
    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=SAMPLE_COINBASE_HOLDINGS,
    )
    registry = MockProviderRegistry({"Coinbase": mock_cb})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 1
    assert entries[0].provider_name == "Coinbase"
    assert entries[0].status == "success"
    assert entries[0].accounts_synced == 1


def test_coinbase_sync_activities_stored(db):
    """Coinbase activities (fills + v2) are persisted and retrievable by account."""
    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=SAMPLE_COINBASE_HOLDINGS,
        activities=SAMPLE_COINBASE_ACTIVITIES,
    )
    registry = MockProviderRegistry({"Coinbase": mock_cb})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    account = db.query(Account).filter_by(external_id="cb_port_001").first()
    activities = (
        db.query(Activity)
        .filter_by(account_id=account.id, provider_name="Coinbase")
        .all()
    )
    assert len(activities) == 3
    ext_ids = {a.external_id for a in activities}
    assert ext_ids == {"fill_001", "fill_002", "v2:recv-001"}

    buy = next(a for a in activities if a.external_id == "fill_001")
    assert buy.type == "buy"
    assert buy.ticker == "BTC"

    v2 = next(a for a in activities if a.external_id == "v2:recv-001")
    assert v2.type == "deposit"
    assert v2.ticker == "BTC"


def test_coinbase_sync_balance_dates_stored(db):
    """Balance dates from Coinbase provider are stored on Account.balance_date."""
    bd = datetime(2026, 1, 28, 18, 0, 0, tzinfo=timezone.utc)
    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=SAMPLE_COINBASE_HOLDINGS,
        balance_dates={
            "cb_port_001": bd,
        },
    )
    registry = MockProviderRegistry({"Coinbase": mock_cb})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    acc = db.query(Account).filter_by(external_id="cb_port_001").first()
    assert acc.balance_date is not None


def test_coinbase_sync_account_upsert_idempotent(db):
    """Syncing Coinbase twice does not duplicate accounts."""
    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=SAMPLE_COINBASE_HOLDINGS,
    )
    registry = MockProviderRegistry({"Coinbase": mock_cb})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)
    service.trigger_sync(db)

    accounts = db.query(Account).filter_by(provider_name="Coinbase").all()
    assert len(accounts) == 1


def test_coinbase_failure_doesnt_block_other_providers(db):
    """Coinbase failure + SimpleFIN success → sync_session.is_complete=True, Coinbase log='failed'."""
    mock_cb = MockCoinbaseClient(should_fail=True)
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS,
    )
    registry = MockProviderRegistry({
        "Coinbase": mock_cb,
        "SimpleFIN": mock_sf,
    })
    service = SyncService(provider_registry=registry)

    # Pre-create a Coinbase account so it gets marked as failed
    _create_accounts(db, "Coinbase", ["cb_port_001"])

    sync_session = service.trigger_sync(db)

    # SimpleFIN succeeded, so sync_session should be complete
    assert sync_session.is_complete is True

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 2
    entry_map = {e.provider_name: e for e in entries}
    assert entry_map["Coinbase"].status == "failed"
    assert entry_map["SimpleFIN"].status == "success"


def test_coinbase_alongside_other_providers(db):
    """Four-provider sync (SnapTrade + SimpleFIN + IBKR + Coinbase) creates separate log entries."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS,
    )
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
    )
    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=SAMPLE_COINBASE_HOLDINGS,
    )
    registry = MockProviderRegistry({
        "SnapTrade": mock_st,
        "SimpleFIN": mock_sf,
        "IBKR": mock_ibkr,
        "Coinbase": mock_cb,
    })
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 4
    provider_names = {e.provider_name for e in entries}
    assert provider_names == {"SnapTrade", "SimpleFIN", "IBKR", "Coinbase"}

    # Accounts are scoped by provider
    st_accounts = db.query(Account).filter_by(provider_name="SnapTrade").all()
    sf_accounts = db.query(Account).filter_by(provider_name="SimpleFIN").all()
    ib_accounts = db.query(Account).filter_by(provider_name="IBKR").all()
    cb_accounts = db.query(Account).filter_by(provider_name="Coinbase").all()
    assert len(st_accounts) == 2
    assert len(sf_accounts) == 3
    assert len(ib_accounts) == 2
    assert len(cb_accounts) == 1


# --- Schwab sync pipeline tests ---


def test_schwab_sync_creates_accounts(db):
    """Schwab sync creates Account records with provider_name='Schwab'."""
    mock_schwab = MockSchwabClient(
        accounts=SAMPLE_SCHWAB_ACCOUNTS,
        holdings=SAMPLE_SCHWAB_HOLDINGS,
    )
    registry = MockProviderRegistry({"Schwab": mock_schwab})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    accounts = db.query(Account).filter_by(provider_name="Schwab").all()
    assert len(accounts) == 2
    assert {a.external_id for a in accounts} == {"HASH_ABC", "HASH_DEF"}
    assert all(a.is_active for a in accounts)
    assert all(a.institution_name == "Charles Schwab" for a in accounts)


def test_schwab_sync_creates_holdings_with_cash(db):
    """Schwab sync creates holdings including _CASH:USD entries."""
    mock_schwab = MockSchwabClient(
        accounts=SAMPLE_SCHWAB_ACCOUNTS,
        holdings=SAMPLE_SCHWAB_HOLDINGS,
    )
    registry = MockProviderRegistry({"Schwab": mock_schwab})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    holdings = db.query(Holding).join(AccountSnapshot).filter(AccountSnapshot.sync_session_id == sync_session.id).all()
    # 5 total: AAPL, GOOGL, _CASH:USD (HASH_ABC) + MSFT, _CASH:USD (HASH_DEF)
    assert len(holdings) == 5

    tickers = {h.ticker for h in holdings}
    assert "AAPL" in tickers
    assert "GOOGL" in tickers
    assert "MSFT" in tickers
    assert "_CASH:USD" in tickers

    # Verify cash holdings have correct values
    cash_holdings = [h for h in holdings if h.ticker == "_CASH:USD"]
    assert len(cash_holdings) == 2
    cash_values = sorted([h.snapshot_value for h in cash_holdings])
    assert cash_values == [Decimal("1000.00"), Decimal("5000.00")]


def test_schwab_sync_creates_log_entry(db):
    """Schwab sync creates a SyncLogEntry with provider_name='Schwab' and status='success'."""
    mock_schwab = MockSchwabClient(
        accounts=SAMPLE_SCHWAB_ACCOUNTS,
        holdings=SAMPLE_SCHWAB_HOLDINGS,
    )
    registry = MockProviderRegistry({"Schwab": mock_schwab})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 1
    assert entries[0].provider_name == "Schwab"
    assert entries[0].status == "success"
    assert entries[0].accounts_synced == 2


def test_schwab_sync_activities_stored(db):
    """Schwab activities are persisted and retrievable by account."""
    mock_schwab = MockSchwabClient(
        accounts=SAMPLE_SCHWAB_ACCOUNTS,
        holdings=SAMPLE_SCHWAB_HOLDINGS,
        activities=SAMPLE_SCHWAB_ACTIVITIES,
    )
    registry = MockProviderRegistry({"Schwab": mock_schwab})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    # Check account HASH_ABC activities (buy + dividend)
    acc_abc = db.query(Account).filter_by(external_id="HASH_ABC").first()
    activities_abc = (
        db.query(Activity)
        .filter_by(account_id=acc_abc.id, provider_name="Schwab")
        .all()
    )
    assert len(activities_abc) == 2
    ext_ids = {a.external_id for a in activities_abc}
    assert ext_ids == {"111222333", "444555666"}

    buy = next(a for a in activities_abc if a.external_id == "111222333")
    assert buy.type == "buy"
    assert buy.ticker == "AAPL"

    dividend = next(a for a in activities_abc if a.external_id == "444555666")
    assert dividend.type == "dividend"
    assert dividend.ticker == "AAPL"

    # Check account HASH_DEF activities (sell)
    acc_def = db.query(Account).filter_by(external_id="HASH_DEF").first()
    activities_def = (
        db.query(Activity)
        .filter_by(account_id=acc_def.id, provider_name="Schwab")
        .all()
    )
    assert len(activities_def) == 1
    assert activities_def[0].external_id == "777888999"
    assert activities_def[0].type == "sell"
    assert activities_def[0].ticker == "MSFT"


def test_schwab_sync_balance_dates_stored(db):
    """Balance dates from Schwab provider are stored on Account.balance_date."""
    bd = datetime(2026, 1, 28, 18, 0, 0, tzinfo=timezone.utc)
    mock_schwab = MockSchwabClient(
        accounts=SAMPLE_SCHWAB_ACCOUNTS,
        holdings=SAMPLE_SCHWAB_HOLDINGS,
        balance_dates={
            "HASH_ABC": bd,
            "HASH_DEF": None,
        },
    )
    registry = MockProviderRegistry({"Schwab": mock_schwab})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    acc_abc = db.query(Account).filter_by(external_id="HASH_ABC").first()
    acc_def = db.query(Account).filter_by(external_id="HASH_DEF").first()

    assert acc_abc.balance_date is not None
    assert acc_def.balance_date is None


def test_schwab_sync_account_upsert_idempotent(db):
    """Syncing Schwab twice does not duplicate accounts."""
    mock_schwab = MockSchwabClient(
        accounts=SAMPLE_SCHWAB_ACCOUNTS,
        holdings=SAMPLE_SCHWAB_HOLDINGS,
    )
    registry = MockProviderRegistry({"Schwab": mock_schwab})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)
    service.trigger_sync(db)

    accounts = db.query(Account).filter_by(provider_name="Schwab").all()
    assert len(accounts) == 2


def test_schwab_failure_doesnt_block_other_providers(db):
    """Schwab failure + SimpleFIN success → sync_session.is_complete=True, Schwab log='failed'."""
    mock_schwab = MockSchwabClient(should_fail=True)
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS,
    )
    registry = MockProviderRegistry({
        "Schwab": mock_schwab,
        "SimpleFIN": mock_sf,
    })
    service = SyncService(provider_registry=registry)

    # Pre-create a Schwab account so it gets marked as failed
    _create_accounts(db, "Schwab", ["HASH_ABC"])

    sync_session = service.trigger_sync(db)

    # SimpleFIN succeeded, so sync_session should be complete
    assert sync_session.is_complete is True

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 2
    entry_map = {e.provider_name: e for e in entries}
    assert entry_map["Schwab"].status == "failed"
    assert entry_map["SimpleFIN"].status == "success"


def test_schwab_alongside_other_providers(db):
    """Five-provider sync creates separate log entries, accounts scoped correctly."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS,
    )
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
    )
    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=SAMPLE_COINBASE_HOLDINGS,
    )
    mock_schwab = MockSchwabClient(
        accounts=SAMPLE_SCHWAB_ACCOUNTS,
        holdings=SAMPLE_SCHWAB_HOLDINGS,
    )
    registry = MockProviderRegistry({
        "SnapTrade": mock_st,
        "SimpleFIN": mock_sf,
        "IBKR": mock_ibkr,
        "Coinbase": mock_cb,
        "Schwab": mock_schwab,
    })
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 5
    provider_names = {e.provider_name for e in entries}
    assert provider_names == {"SnapTrade", "SimpleFIN", "IBKR", "Coinbase", "Schwab"}

    # Accounts are scoped by provider
    st_accounts = db.query(Account).filter_by(provider_name="SnapTrade").all()
    sf_accounts = db.query(Account).filter_by(provider_name="SimpleFIN").all()
    ib_accounts = db.query(Account).filter_by(provider_name="IBKR").all()
    cb_accounts = db.query(Account).filter_by(provider_name="Coinbase").all()
    sw_accounts = db.query(Account).filter_by(provider_name="Schwab").all()
    assert len(st_accounts) == 2
    assert len(sf_accounts) == 3
    assert len(ib_accounts) == 2
    assert len(cb_accounts) == 1
    assert len(sw_accounts) == 2


def test_sync_does_not_affect_manual_accounts(db):
    """Manual accounts should be untouched by provider sync."""
    # Create a manual account with a holding
    manual_acct = ManualHoldingsService.create_manual_account(db, "My House")
    ManualHoldingsService.add_holding(
        db, manual_acct,
        ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
    )

    # Record the snapshot state before sync
    holdings_before = ManualHoldingsService.get_current_holdings(db, manual_acct.id)
    assert len(holdings_before) == 1
    snap_before = (
        db.query(AccountSnapshot)
        .filter(AccountSnapshot.account_id == manual_acct.id)
        .all()
    )
    snap_count_before = len(snap_before)

    # Trigger a sync with a SnapTrade provider
    mock_client = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_client})
    service = SyncService(provider_registry=registry)
    service.trigger_sync(db)

    # Manual account should be untouched
    holdings_after = ManualHoldingsService.get_current_holdings(db, manual_acct.id)
    assert len(holdings_after) == 1
    assert holdings_after[0].ticker == "HOME"
    assert holdings_after[0].snapshot_value == Decimal("500000")

    snap_after = (
        db.query(AccountSnapshot)
        .filter(AccountSnapshot.account_id == manual_acct.id)
        .all()
    )
    assert len(snap_after) == snap_count_before


def test_sync_creates_daily_holding_values(db):
    """Sync should create DailyHoldingValue rows for each holding."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    # Should have created DailyHoldingValue rows matching holdings
    holdings = db.query(Holding).all()
    dhv_rows = db.query(DailyHoldingValue).all()
    assert len(dhv_rows) == len(holdings)
    assert len(dhv_rows) > 0

    # Verify DHV values match holding snapshot values
    for dhv in dhv_rows:
        matching_holding = next(
            h for h in holdings
            if h.security_id == dhv.security_id
            and h.account_snapshot_id == dhv.account_snapshot_id
        )
        assert dhv.close_price == matching_holding.snapshot_price
        assert dhv.market_value == matching_holding.snapshot_value


# --- Stale data handling tests ---


def test_stale_balance_date_skips_snapshot_creation(db):
    """Same balance_date → no new AccountSnapshot created."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    # First sync: establishes balance_date on account
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],  # Just sf_acc_001
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    snap_count_after_first = db.query(AccountSnapshot).count()
    assert snap_count_after_first == 1

    # Second sync: same balance_date → stale
    service.trigger_sync(db)

    snap_count_after_second = db.query(AccountSnapshot).count()
    assert snap_count_after_second == snap_count_after_first

    acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    assert acc.last_sync_status == "stale"


def test_fresh_balance_date_creates_snapshot(db):
    """Newer balance_date → new snapshot created."""
    bd_old = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)
    bd_new = datetime(2026, 1, 29, 12, 0, 0, tzinfo=timezone.utc)

    # First sync
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={"sf_acc_001": bd_old},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)
    snap_count_first = db.query(AccountSnapshot).count()

    # Second sync with newer balance_date
    mock_sf2 = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={"sf_acc_001": bd_new},
    )
    registry2 = MockProviderRegistry({"SimpleFIN": mock_sf2})
    service2 = SyncService(provider_registry=registry2)

    service2.trigger_sync(db)
    snap_count_second = db.query(AccountSnapshot).count()

    assert snap_count_second == snap_count_first + 1

    acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    assert acc.last_sync_status == "success"


def test_first_sync_no_previous_balance_date_creates_snapshot(db):
    """Null existing balance_date → always creates snapshot (first sync)."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    # First sync should always create a snapshot
    assert db.query(AccountSnapshot).count() == 1
    acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    assert acc.last_sync_status == "success"
    assert acc.balance_date is not None


def test_null_new_balance_date_creates_snapshot(db):
    """Null incoming balance_date → always creates snapshot (e.g., Coinbase/Schwab)."""
    bd_existing = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    # Pre-create account with an existing balance_date
    acc = Account(
        provider_name="Coinbase",
        external_id="cb_port_001",
        name="Default Portfolio",
        institution_name="Coinbase",
        is_active=True,
        balance_date=bd_existing,
    )
    db.add(acc)
    db.commit()

    # Sync with no balance_date (Coinbase doesn't provide them)
    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=SAMPLE_COINBASE_HOLDINGS,
        balance_dates={},  # No balance dates
    )
    registry = MockProviderRegistry({"Coinbase": mock_cb})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    assert db.query(AccountSnapshot).count() == 1
    db.refresh(acc)
    assert acc.last_sync_status == "success"


def test_stale_account_preserves_existing_holdings(db):
    """When second sync is stale, first sync's holdings still valid."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    # First sync creates holdings
    service.trigger_sync(db)
    holdings_count = db.query(Holding).count()
    assert holdings_count > 0  # sf_acc_001 has _CASH:USD from balance

    # Second sync with same date → stale, no new holdings
    service.trigger_sync(db)
    assert db.query(Holding).count() == holdings_count


def test_all_accounts_stale_sync_session_still_complete(db):
    """All stale → is_complete=True, accounts_synced=0, accounts_stale>0."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    # First sync to establish balance_date
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    # Second sync: all stale
    sync_session = service.trigger_sync(db)

    assert sync_session.is_complete is True

    # Check the second session's log entry
    entries = (
        db.query(SyncLogEntry)
        .filter_by(sync_session_id=sync_session.id)
        .all()
    )
    assert len(entries) == 1
    assert entries[0].accounts_synced == 0
    assert entries[0].accounts_stale == 1


def test_parse_simplefin_error_sets_account_status(db):
    """Error matching account institution → last_sync_error persists when data is stale."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    # First sync: establishes balance_date
    mock_sf_first = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],  # sf_acc_001: Chase Bank
        balance_dates={"sf_acc_001": bd},
    )
    registry_first = MockProviderRegistry({"SimpleFIN": mock_sf_first})
    SyncService(provider_registry=registry_first).trigger_sync(db)

    # Second sync: same balance_date + error → staleness gate runs, error persists
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        errors=["Connection to Chase Bank may need attention"],
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    SyncService(provider_registry=registry).trigger_sync(db)

    acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    # Error parsing sets last_sync_error, staleness gate sets status to "stale"
    # but doesn't clear last_sync_error
    assert acc.last_sync_error == "Connection to Chase Bank may need attention"
    assert acc.last_sync_status == "stale"


def test_parse_simplefin_error_no_match_leaves_unchanged(db):
    """Error not matching any account → accounts unaffected."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],  # Chase Bank
        errors=["Connection to Unknown Bank may need attention"],
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    # No match, so last_sync_error should be None (cleared by sync_account success path)
    assert acc.last_sync_error is None


def test_parse_simplefin_error_case_insensitive(db):
    """Case-insensitive match: 'chase bank' vs 'Chase Bank'."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    # First sync: establishes balance_date
    mock_sf_first = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={"sf_acc_001": bd},
    )
    registry_first = MockProviderRegistry({"SimpleFIN": mock_sf_first})
    SyncService(provider_registry=registry_first).trigger_sync(db)

    # Second sync: same date + case-mismatched error
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],  # "Chase Bank"
        errors=["Connection to chase bank may need attention"],
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    SyncService(provider_registry=registry).trigger_sync(db)

    acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    assert acc.last_sync_error == "Connection to chase bank may need attention"


def test_account_snapshot_stores_balance_date(db):
    """balance_date is saved on AccountSnapshot."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    snaps = (
        db.query(AccountSnapshot)
        .filter_by(sync_session_id=sync_session.id)
        .all()
    )
    assert len(snaps) == 1
    # SQLite strips timezone info, so compare as naive UTC
    assert snaps[0].balance_date == bd.replace(tzinfo=None)


def test_stale_account_updates_last_sync_time(db):
    """Even when stale, last_sync_time still advances."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    # First sync
    service.trigger_sync(db)
    acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    first_sync_time = acc.last_sync_time
    assert first_sync_time is not None

    # Second sync: stale but last_sync_time should advance
    service.trigger_sync(db)
    db.refresh(acc)
    assert acc.last_sync_status == "stale"
    assert acc.last_sync_time >= first_sync_time


def test_accounts_missing_from_provider_response_are_skipped(db):
    """Accounts not in provider response should not be synced (no empty snapshots)."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    # First sync: both SimpleFIN accounts synced normally
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:2],
        balance_dates={"sf_acc_001": bd, "sf_acc_002": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)
    service.trigger_sync(db)

    acc1 = db.query(Account).filter_by(external_id="sf_acc_001").first()
    acc2 = db.query(Account).filter_by(external_id="sf_acc_002").first()
    assert acc1 is not None and acc2 is not None

    snapshots_before_acc1 = (
        db.query(AccountSnapshot).filter_by(account_id=acc1.id).count()
    )
    snapshots_before_acc2 = (
        db.query(AccountSnapshot).filter_by(account_id=acc2.id).count()
    )
    assert snapshots_before_acc1 == 1
    assert snapshots_before_acc2 == 1

    # Second sync: provider only returns acc_001 (acc_002 dropped from response)
    new_bd = datetime(2026, 1, 29, 12, 0, 0, tzinfo=timezone.utc)
    mock_sf2 = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],  # only acc_001
        balance_dates={"sf_acc_001": new_bd},
    )
    registry2 = MockProviderRegistry({"SimpleFIN": mock_sf2})
    service2 = SyncService(provider_registry=registry2)
    service2.trigger_sync(db)

    # acc_001 should have a new snapshot (fresh balance_date)
    snapshots_after_acc1 = (
        db.query(AccountSnapshot).filter_by(account_id=acc1.id).count()
    )
    assert snapshots_after_acc1 == 2

    # acc_002 should NOT have a new snapshot — it wasn't in the response
    snapshots_after_acc2 = (
        db.query(AccountSnapshot).filter_by(account_id=acc2.id).count()
    )
    assert snapshots_after_acc2 == snapshots_before_acc2

    # acc_002 should be marked as skipped with an error message
    db.refresh(acc2)
    assert acc2.last_sync_status == "skipped"
    assert "not returned by provider" in acc2.last_sync_error
    assert acc2.last_sync_time is not None


# --- Duplicate holding consolidation tests ---


def test_duplicate_holdings_consolidated(db):
    """Duplicate holdings with the same symbol are merged (quantities and values summed)."""
    from integrations.provider_protocol import ProviderHolding

    duplicate_holdings = [
        ProviderHolding(
            account_id="cb_port_001",
            symbol="_CASH:USD",
            name="US Dollar",
            quantity=Decimal("8.73"),
            price=Decimal("1"),
            market_value=Decimal("8.73"),
            currency="USD",
        ),
        ProviderHolding(
            account_id="cb_port_001",
            symbol="_CASH:USD",
            name="US Dollar",
            quantity=Decimal("26.00"),
            price=Decimal("1"),
            market_value=Decimal("26.00"),
            currency="USD",
        ),
        ProviderHolding(
            account_id="cb_port_001",
            symbol="BTC",
            name="Bitcoin",
            quantity=Decimal("0.5"),
            price=Decimal("50000"),
            market_value=Decimal("25000"),
            currency="USD",
        ),
    ]

    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=duplicate_holdings,
    )
    registry = MockProviderRegistry({"Coinbase": mock_cb})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    holdings = (
        db.query(Holding)
        .join(AccountSnapshot)
        .filter(AccountSnapshot.sync_session_id == sync_session.id)
        .all()
    )
    # 2 holdings: consolidated _CASH:USD + BTC
    assert len(holdings) == 2

    tickers = {h.ticker for h in holdings}
    assert tickers == {"_CASH:USD", "BTC"}

    cash = next(h for h in holdings if h.ticker == "_CASH:USD")
    assert cash.quantity == Decimal("34.73")
    assert cash.snapshot_value == Decimal("34.73")
    assert cash.snapshot_price == Decimal("1")

    btc = next(h for h in holdings if h.ticker == "BTC")
    assert btc.quantity == Decimal("0.5")
    assert btc.snapshot_value == Decimal("25000")


def test_duplicate_holdings_sync_succeeds(db):
    """Sync succeeds (no IntegrityError) when provider returns duplicate symbols."""
    from integrations.provider_protocol import ProviderHolding

    duplicate_holdings = [
        ProviderHolding(
            account_id="cb_port_001",
            symbol="_CASH:USD",
            name="US Dollar",
            quantity=Decimal("8.73"),
            price=Decimal("1"),
            market_value=Decimal("8.73"),
            currency="USD",
        ),
        ProviderHolding(
            account_id="cb_port_001",
            symbol="_CASH:USD",
            name="US Dollar",
            quantity=Decimal("26.00"),
            price=Decimal("1"),
            market_value=Decimal("26.00"),
            currency="USD",
        ),
    ]

    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=duplicate_holdings,
    )
    registry = MockProviderRegistry({"Coinbase": mock_cb})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    assert sync_session.is_complete is True
    acc = db.query(Account).filter_by(external_id="cb_port_001").first()
    assert acc.last_sync_status == "success"


def test_duplicate_holdings_logs_warning(db, caplog):
    """A warning is logged when duplicate holdings are merged."""
    import logging

    from integrations.provider_protocol import ProviderHolding

    duplicate_holdings = [
        ProviderHolding(
            account_id="cb_port_001",
            symbol="_CASH:USD",
            name="US Dollar",
            quantity=Decimal("8.73"),
            price=Decimal("1"),
            market_value=Decimal("8.73"),
            currency="USD",
        ),
        ProviderHolding(
            account_id="cb_port_001",
            symbol="_CASH:USD",
            name="US Dollar",
            quantity=Decimal("26.00"),
            price=Decimal("1"),
            market_value=Decimal("26.00"),
            currency="USD",
        ),
    ]

    mock_cb = MockCoinbaseClient(
        accounts=SAMPLE_COINBASE_ACCOUNTS,
        holdings=duplicate_holdings,
    )
    registry = MockProviderRegistry({"Coinbase": mock_cb})
    service = SyncService(provider_registry=registry)

    with caplog.at_level(logging.WARNING, logger="services.sync_service"):
        service.trigger_sync(db)

    assert any(
        "Merged" in record.message and "_CASH:USD" in record.message
        for record in caplog.records
    )


# --- Provider error guard tests ---


def test_provider_errors_with_no_data_skips_all_accounts(db):
    """Provider errors + empty response → all accounts marked 'error', no new snapshots."""
    # Pre-create accounts (simulating a previous successful sync)
    accounts = _create_accounts(db, "IBKR", ["ib_acc_001", "ib_acc_002"])

    # Provider returns errors but no holdings/accounts/balance_dates
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=[],
        errors=["Statement could not be generated"],
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    # No new AccountSnapshots should be created
    snaps = db.query(AccountSnapshot).filter_by(sync_session_id=sync_session.id).all()
    assert len(snaps) == 0

    # All accounts should be marked as error
    for acc in accounts:
        db.refresh(acc)
        assert acc.last_sync_status == "error"
        assert "Statement could not be generated" in acc.last_sync_error
        assert acc.last_sync_time is not None


def test_provider_errors_with_partial_data_syncs_valid_accounts(db):
    """Provider errors + some valid data → sync valid accounts, error-skip empty ones."""
    from integrations.provider_protocol import ProviderHolding

    # Pre-create accounts
    _create_accounts(db, "IBKR", ["ib_acc_001", "ib_acc_002"])

    # Provider returns errors + holdings only for acc_001
    partial_holdings = [
        ProviderHolding(
            account_id="ib_acc_001",
            symbol="AAPL",
            name="Apple Inc.",
            quantity=Decimal("10"),
            price=Decimal("150"),
            market_value=Decimal("1500"),
            currency="USD",
        ),
    ]
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=partial_holdings,
        errors=["Statement could not be generated for sub-account"],
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    # acc_001 should have a snapshot (it had holdings)
    acc1 = db.query(Account).filter_by(external_id="ib_acc_001").first()
    snaps_1 = db.query(AccountSnapshot).filter_by(
        sync_session_id=sync_session.id, account_id=acc1.id
    ).all()
    assert len(snaps_1) == 1
    assert snaps_1[0].status == "success"

    # acc_002 should NOT have a snapshot (no data + errors)
    acc2 = db.query(Account).filter_by(external_id="ib_acc_002").first()
    snaps_2 = db.query(AccountSnapshot).filter_by(
        sync_session_id=sync_session.id, account_id=acc2.id
    ).all()
    assert len(snaps_2) == 0
    assert acc2.last_sync_status == "error"

    # Log entry should be "partial" (errors + some success)
    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 1
    assert entries[0].status == "partial"


def test_provider_error_messages_joined_in_last_sync_error(db):
    """Multiple provider errors are joined with '; ' in last_sync_error."""
    _create_accounts(db, "IBKR", ["ib_acc_001"])

    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=[],
        errors=["Error one", "Error two"],
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    acc = db.query(Account).filter_by(external_id="ib_acc_001").first()
    assert acc.last_sync_status == "error"
    assert acc.last_sync_error == "Error one; Error two"


def test_provider_errors_preserve_previous_data(db):
    """First sync succeeds, second fails with errors → no new snapshot, original preserved."""
    # First sync: success with holdings
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    first_session = service.trigger_sync(db)

    acc1 = db.query(Account).filter_by(external_id="ib_acc_001").first()
    first_snaps = db.query(AccountSnapshot).filter_by(account_id=acc1.id).all()
    assert len(first_snaps) == 1
    assert first_snaps[0].total_value > 0

    # Second sync: errors + no data
    mock_ibkr2 = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=[],
        errors=["Statement could not be generated"],
    )
    registry2 = MockProviderRegistry({"IBKR": mock_ibkr2})
    service2 = SyncService(provider_registry=registry2)

    service2.trigger_sync(db)

    # Original snapshot still there, no new one created
    all_snaps = db.query(AccountSnapshot).filter_by(account_id=acc1.id).all()
    assert len(all_snaps) == 1  # Same as before
    assert all_snaps[0].sync_session_id == first_session.id

    db.refresh(acc1)
    assert acc1.last_sync_status == "error"


def test_zero_holdings_without_errors_syncs_normally(db):
    """Liquidated account (0 holdings, no errors) still syncs — no false positive."""
    from integrations.provider_protocol import ProviderAccount

    liquidated_accounts = [
        ProviderAccount(
            id="liq_001",
            name="Liquidated Account",
            institution="Interactive Brokers",
            account_number=None,
        ),
    ]
    mock_ibkr = MockIBKRFlexClient(
        accounts=liquidated_accounts,
        holdings=[],  # Legitimately empty
        # No errors
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    acc = db.query(Account).filter_by(external_id="liq_001").first()
    assert acc.last_sync_status == "success"

    snaps = db.query(AccountSnapshot).filter_by(sync_session_id=sync_session.id).all()
    assert len(snaps) == 1
    assert snaps[0].status == "success"
    assert Decimal(str(snaps[0].total_value)) == Decimal("0")


def test_balance_date_present_with_errors_still_syncs(db):
    """Account with balance_date but no holdings + errors → still syncs (provider had data)."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    _create_accounts(db, "SimpleFIN", ["sf_acc_001"])

    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        errors=["Some transient error"],
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    # Account should have synced because balance_date was present
    assert acc.last_sync_status == "success"

    snaps = db.query(AccountSnapshot).filter_by(sync_session_id=sync_session.id).all()
    assert len(snaps) == 1


def test_error_skipped_accounts_tracked_in_log_entry(db):
    """accounts_error field is populated in SyncLogEntry."""
    _create_accounts(db, "IBKR", ["ib_acc_001", "ib_acc_002"])

    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=[],
        errors=["Statement could not be generated"],
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 1
    assert entries[0].accounts_error == 2
    assert entries[0].accounts_synced == 0
    assert entries[0].status == "failed"


def test_all_error_skipped_log_status_failed(db):
    """All accounts error-skipped → log status is 'failed'."""
    _create_accounts(db, "IBKR", ["ib_acc_001"])

    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS[:1],
        holdings=[],
        errors=["API unavailable"],
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert entries[0].status == "failed"


def test_soft_error_one_provider_doesnt_affect_other(db):
    """IBKR soft error (errors + empty data) doesn't affect SimpleFIN accounts."""
    _create_accounts(db, "IBKR", ["ib_acc_001", "ib_acc_002"])

    # IBKR: errors + no data (soft failure)
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=[],
        errors=["Statement could not be generated"],
    )
    # SimpleFIN: normal success
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={"sf_acc_001": datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)},
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr, "SimpleFIN": mock_sf})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    # Session should be complete (SimpleFIN succeeded)
    assert sync_session.is_complete is True

    # IBKR accounts should be error-skipped
    ib1 = db.query(Account).filter_by(external_id="ib_acc_001").first()
    ib2 = db.query(Account).filter_by(external_id="ib_acc_002").first()
    assert ib1.last_sync_status == "error"
    assert ib2.last_sync_status == "error"

    # SimpleFIN account should have synced successfully
    sf1 = db.query(Account).filter_by(external_id="sf_acc_001").first()
    assert sf1.last_sync_status == "success"

    # No IBKR snapshots, one SimpleFIN snapshot
    ib_snaps = db.query(AccountSnapshot).filter_by(account_id=ib1.id).count()
    sf_snaps = db.query(AccountSnapshot).filter_by(account_id=sf1.id).count()
    assert ib_snaps == 0
    assert sf_snaps == 1

    # Log entries: IBKR failed, SimpleFIN success
    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    entry_map = {e.provider_name: e for e in entries}
    assert entry_map["IBKR"].status == "failed"
    assert entry_map["IBKR"].accounts_error == 2
    assert entry_map["SimpleFIN"].status == "success"


# --- Sentinel DHV tests for zero-holding accounts ---


def test_sync_zero_holdings_writes_sentinel_dhv(db):
    """Sync with zero holdings writes a _ZERO_BALANCE sentinel DHV row."""
    from integrations.provider_protocol import ProviderAccount
    from utils.ticker import ZERO_BALANCE_TICKER

    liquidated_accounts = [
        ProviderAccount(
            id="liq_001",
            name="Liquidated Account",
            institution="Interactive Brokers",
            account_number=None,
        ),
    ]
    mock_ibkr = MockIBKRFlexClient(
        accounts=liquidated_accounts,
        holdings=[],  # Legitimately empty
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    service.trigger_sync(db)

    # Should have a sentinel DHV row
    dhv_rows = db.query(DailyHoldingValue).all()
    assert len(dhv_rows) == 1
    assert dhv_rows[0].ticker == ZERO_BALANCE_TICKER
    assert dhv_rows[0].market_value == Decimal("0")

    # Security should exist
    security = db.query(Security).filter_by(ticker=ZERO_BALANCE_TICKER).first()
    assert security is not None


def test_resync_with_real_holdings_deletes_sentinel(db):
    """Re-syncing with real holdings deletes the sentinel DHV row."""
    from integrations.provider_protocol import ProviderAccount, ProviderHolding
    from utils.ticker import ZERO_BALANCE_TICKER

    account_data = [
        ProviderAccount(
            id="acc_001",
            name="Test Account",
            institution="TestBroker",
            account_number=None,
        ),
    ]

    # First sync: no holdings → sentinel
    mock1 = MockIBKRFlexClient(accounts=account_data, holdings=[])
    registry1 = MockProviderRegistry({"IBKR": mock1})
    SyncService(provider_registry=registry1).trigger_sync(db)

    sentinel_rows = db.query(DailyHoldingValue).filter(
        DailyHoldingValue.ticker == ZERO_BALANCE_TICKER
    ).count()
    assert sentinel_rows == 1

    # Second sync: has holdings → sentinel deleted
    holdings = [
        ProviderHolding(
            account_id="acc_001",
            symbol="AAPL",
            name="Apple Inc.",
            quantity=Decimal("10"),
            price=Decimal("150"),
            market_value=Decimal("1500"),
            currency="USD",
        ),
    ]
    mock2 = MockIBKRFlexClient(accounts=account_data, holdings=holdings)
    registry2 = MockProviderRegistry({"IBKR": mock2})
    SyncService(provider_registry=registry2).trigger_sync(db)

    # Sentinel should be gone, real DHV should exist
    sentinel_rows = db.query(DailyHoldingValue).filter(
        DailyHoldingValue.ticker == ZERO_BALANCE_TICKER
    ).count()
    assert sentinel_rows == 0

    real_rows = db.query(DailyHoldingValue).filter(
        DailyHoldingValue.ticker == "AAPL"
    ).count()
    assert real_rows == 1


def test_resync_back_to_zero_replaces_real_with_sentinel(db):
    """Re-syncing back to zero holdings replaces real DHVs with sentinel."""
    from integrations.provider_protocol import ProviderAccount, ProviderHolding
    from utils.ticker import ZERO_BALANCE_TICKER

    account_data = [
        ProviderAccount(
            id="acc_001",
            name="Test Account",
            institution="TestBroker",
            account_number=None,
        ),
    ]

    # First sync: has holdings
    holdings = [
        ProviderHolding(
            account_id="acc_001",
            symbol="AAPL",
            name="Apple Inc.",
            quantity=Decimal("10"),
            price=Decimal("150"),
            market_value=Decimal("1500"),
            currency="USD",
        ),
    ]
    mock1 = MockIBKRFlexClient(accounts=account_data, holdings=holdings)
    registry1 = MockProviderRegistry({"IBKR": mock1})
    SyncService(provider_registry=registry1).trigger_sync(db)

    real_rows = db.query(DailyHoldingValue).filter(
        DailyHoldingValue.ticker == "AAPL"
    ).count()
    assert real_rows == 1

    # Second sync: liquidated
    mock2 = MockIBKRFlexClient(accounts=account_data, holdings=[])
    registry2 = MockProviderRegistry({"IBKR": mock2})
    SyncService(provider_registry=registry2).trigger_sync(db)

    # Real DHV should be gone, sentinel should exist
    real_rows = db.query(DailyHoldingValue).filter(
        DailyHoldingValue.ticker == "AAPL"
    ).count()
    assert real_rows == 0

    sentinel_rows = db.query(DailyHoldingValue).filter(
        DailyHoldingValue.ticker == ZERO_BALANCE_TICKER
    ).count()
    assert sentinel_rows == 1


# --- Concurrent sync lock tests ---


def test_concurrent_sync_raises_value_error(db):
    """Second concurrent sync raises ValueError while first is running."""
    import threading

    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    # Use threading events for reliable synchronization
    first_sync_started = threading.Event()
    proceed_with_first_sync = threading.Event()
    second_sync_error = None

    def run_first_sync():
        """First sync - will signal when it starts."""
        # Monkey-patch _sync_provider_accounts to add a delay
        original_method = service._sync_provider_accounts

        def delayed_sync(*args, **kwargs):
            first_sync_started.set()  # Signal that we've acquired the lock
            proceed_with_first_sync.wait()  # Wait for test to try second sync
            return original_method(*args, **kwargs)

        service._sync_provider_accounts = delayed_sync
        service.trigger_sync(db)
        service._sync_provider_accounts = original_method

    def run_second_sync():
        """Second sync - should fail immediately."""
        nonlocal second_sync_error
        try:
            service.trigger_sync(db)
        except ValueError as e:
            second_sync_error = str(e)

    # Start first sync in background
    t1 = threading.Thread(target=run_first_sync)
    t1.start()

    # Wait for first sync to acquire lock
    first_sync_started.wait(timeout=1.0)

    # Try second sync - should fail immediately
    run_second_sync()

    # Let first sync continue and complete
    proceed_with_first_sync.set()
    t1.join()

    # Verify second sync got ValueError
    assert second_sync_error is not None
    assert "already in progress" in second_sync_error.lower()


def test_sync_lock_released_after_completion(db):
    """Lock is released after successful sync."""
    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    # First sync
    service.trigger_sync(db)

    # Lock should be released, so is_sync_in_progress should be False
    assert service.is_sync_in_progress() is False

    # Second sync should succeed
    service.trigger_sync(db)
    assert service.is_sync_in_progress() is False


def test_sync_lock_released_after_error(db):
    """Lock is released even if sync fails."""
    mock_st = MockSnapTradeClient(
        should_fail=True,
        failure_message="SnapTrade API unavailable",
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    # Pre-create an account so it gets marked as failed
    _create_accounts(db, "SnapTrade", ["st_acc_001"])

    # Sync will fail but should still release lock
    sync_session = service.trigger_sync(db)
    assert sync_session.is_complete is False

    # Lock should be released
    assert service.is_sync_in_progress() is False


def test_is_sync_in_progress(db):
    """is_sync_in_progress() accurately reflects lock state."""
    import threading

    mock_st = MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    # Initially no sync running
    assert service.is_sync_in_progress() is False

    # Use threading events for reliable synchronization
    sync_started = threading.Event()
    proceed_with_sync = threading.Event()

    def run_sync():
        """Run sync with delay to hold the lock."""
        original_method = service._sync_provider_accounts

        def delayed_sync(*args, **kwargs):
            sync_started.set()
            proceed_with_sync.wait()
            return original_method(*args, **kwargs)

        service._sync_provider_accounts = delayed_sync
        service.trigger_sync(db)
        service._sync_provider_accounts = original_method

    # Start sync in background
    t = threading.Thread(target=run_sync)
    t.start()

    # Wait for sync to acquire lock
    sync_started.wait(timeout=1.0)

    # Should report sync in progress
    assert service.is_sync_in_progress() is True

    # Let sync complete
    proceed_with_sync.set()
    t.join()

    # Should report no sync in progress
    assert service.is_sync_in_progress() is False


# --- Typed exception handling tests ---


def test_provider_auth_error_marks_accounts_failed(db):
    """A ProviderAuthError from sync_all() marks all provider accounts as failed."""
    _create_accounts(db, "SnapTrade", ["st_acc_001"])

    mock_st = MockSnapTradeClient(
        should_fail=True,
        failure_message="SnapTrade token expired",
        failure_type="auth",
    )
    registry = MockProviderRegistry({"SnapTrade": mock_st})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    assert sync_session.is_complete is False
    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 1
    assert entries[0].status == "failed"
    assert "SnapTrade token expired" in entries[0].error_messages[0]

    acc = db.query(Account).filter_by(external_id="st_acc_001").first()
    assert acc.last_sync_status == "failed"
    assert "SnapTrade token expired" in acc.last_sync_error


def test_provider_connection_error_marks_accounts_failed(db):
    """A ProviderConnectionError from sync_all() marks all provider accounts as failed."""
    _create_accounts(db, "IBKR", ["ib_acc_001"])

    mock_ibkr = MockIBKRFlexClient(
        should_fail=True,
        failure_type="connection",
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    assert sync_session.is_complete is False
    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 1
    assert entries[0].status == "failed"

    acc = db.query(Account).filter_by(external_id="ib_acc_001").first()
    assert acc.last_sync_status == "failed"


def test_typed_exception_doesnt_block_other_providers(db):
    """One provider failing with a typed error doesn't prevent other providers from syncing."""
    _create_accounts(db, "SnapTrade", ["st_acc_001"])

    mock_st = MockSnapTradeClient(
        should_fail=True,
        failure_message="Auth expired",
        failure_type="auth",
    )
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={"sf_acc_001": datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)},
    )
    registry = MockProviderRegistry({
        "SnapTrade": mock_st,
        "SimpleFIN": mock_sf,
    })
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    # SimpleFIN should have synced successfully
    assert sync_session.is_complete is True
    entries = db.query(SyncLogEntry).filter_by(sync_session_id=sync_session.id).all()
    assert len(entries) == 2

    sf_entry = next(e for e in entries if e.provider_name == "SimpleFIN")
    assert sf_entry.status == "success"

    st_entry = next(e for e in entries if e.provider_name == "SnapTrade")
    assert st_entry.status == "failed"

    # SnapTrade account should be failed, SimpleFIN account should be success
    st_acc = db.query(Account).filter_by(external_id="st_acc_001").first()
    assert st_acc.last_sync_status == "failed"

    sf_acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    assert sf_acc.last_sync_status == "success"


def test_structured_errors_match_by_institution_name(db):
    """ProviderSyncError with institution_name matches account directly (no regex)."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    # First sync to establish balance_date
    mock_sf_first = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],  # Chase Bank
        balance_dates={"sf_acc_001": bd},
    )
    registry_first = MockProviderRegistry({"SimpleFIN": mock_sf_first})
    SyncService(provider_registry=registry_first).trigger_sync(db)

    # Second sync with structured error carrying institution_name
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        errors=[ProviderSyncError(
            message="Institution connection issue",
            category=ErrorCategory.CONNECTION,
            institution_name="Chase Bank",
            retriable=True,
        )],
        balance_dates={"sf_acc_001": bd},
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    SyncService(provider_registry=registry).trigger_sync(db)

    acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    assert acc.last_sync_error == "Institution connection issue"


def test_structured_errors_match_by_account_id(db):
    """ProviderSyncError with account_id matches the specific account."""
    bd = datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc)

    # First sync to establish balance_date
    mock_sf_first = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:2],  # Chase + Schwab
        balance_dates={
            "sf_acc_001": bd,
            "sf_acc_002": bd,
        },
    )
    registry_first = MockProviderRegistry({"SimpleFIN": mock_sf_first})
    SyncService(provider_registry=registry_first).trigger_sync(db)

    # Second sync with account-scoped error
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:2],
        errors=[ProviderSyncError(
            message="Account-specific error",
            category=ErrorCategory.DATA,
            account_id="sf_acc_001",
        )],
        balance_dates={
            "sf_acc_001": bd,
            "sf_acc_002": bd,
        },
    )
    registry = MockProviderRegistry({"SimpleFIN": mock_sf})
    SyncService(provider_registry=registry).trigger_sync(db)

    # Only sf_acc_001 should be marked as error
    acc1 = db.query(Account).filter_by(external_id="sf_acc_001").first()
    assert acc1.last_sync_error == "Account-specific error"

    # sf_acc_002 should be stale (same balance_date), not error
    acc2 = db.query(Account).filter_by(external_id="sf_acc_002").first()
    assert acc2.last_sync_status == "stale"


# --- Transaction safety / savepoint tests ---


def test_activity_sync_failure_rolls_back_cleanly(db):
    """Activity sync failure (with savepoint) does not leave stale activity rows.

    Holdings should still be committed; only the activity writes are rolled back.
    """
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
        activities=SAMPLE_IBKR_ACTIVITIES,
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    with patch(
        "services.sync_service.ActivityService.sync_activities",
        side_effect=RuntimeError("activity sync exploded"),
    ):
        sync_session = service.trigger_sync(db)

    # Holdings should be committed despite activity failure
    assert sync_session.is_complete is True
    holdings = (
        db.query(Holding)
        .join(AccountSnapshot)
        .filter(AccountSnapshot.sync_session_id == sync_session.id)
        .all()
    )
    assert len(holdings) > 0

    # No activity rows should have leaked into the DB
    activities = db.query(Activity).all()
    assert len(activities) == 0


def test_lot_reconciliation_failure_rolls_back_cleanly(db):
    """Lot reconciliation failure does not leave orphan data.

    Holdings should still be committed; only the reconciliation writes
    are rolled back by the savepoint.
    """
    mock_ibkr = MockIBKRFlexClient(
        accounts=SAMPLE_IBKR_ACCOUNTS,
        holdings=SAMPLE_IBKR_HOLDINGS,
    )
    registry = MockProviderRegistry({"IBKR": mock_ibkr})
    service = SyncService(provider_registry=registry)

    with patch(
        "services.sync_service.LotReconciliationService.reconcile_account",
        side_effect=RuntimeError("reconciliation exploded"),
    ):
        sync_session = service.trigger_sync(db)

    # Holdings should be committed despite reconciliation failure
    assert sync_session.is_complete is True
    holdings = (
        db.query(Holding)
        .join(AccountSnapshot)
        .filter(AccountSnapshot.sync_session_id == sync_session.id)
        .all()
    )
    assert len(holdings) > 0

    # Accounts should show success (reconciliation is best-effort)
    for acc in db.query(Account).filter_by(provider_name="IBKR").all():
        assert acc.last_sync_status == "success"


def test_provider_failure_doesnt_contaminate_other_providers(db):
    """First provider fails mid-sync; second provider's data commits cleanly.

    The per-provider savepoint ensures a partial flush from the failing
    provider is rolled back before the next provider runs.
    """
    # Pre-create a SnapTrade account so failure marking works
    _create_accounts(db, "SnapTrade", ["st_acc_001"])

    # SnapTrade will fail (raises inside sync_all)
    mock_st = MockSnapTradeClient(
        should_fail=True,
        failure_message="SnapTrade API down",
    )
    # SimpleFIN will succeed
    mock_sf = MockSimpleFINClient(
        accounts=SAMPLE_SIMPLEFIN_ACCOUNTS[:1],
        balance_dates={
            "sf_acc_001": datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc),
        },
    )
    registry = MockProviderRegistry({
        "SnapTrade": mock_st,
        "SimpleFIN": mock_sf,
    })
    service = SyncService(provider_registry=registry)

    sync_session = service.trigger_sync(db)

    # Sync session should be complete (SimpleFIN succeeded)
    assert sync_session.is_complete is True

    # SimpleFIN account synced successfully
    sf_acc = db.query(Account).filter_by(external_id="sf_acc_001").first()
    assert sf_acc.last_sync_status == "success"

    # SimpleFIN has holdings committed
    sf_snaps = (
        db.query(AccountSnapshot)
        .filter_by(account_id=sf_acc.id, sync_session_id=sync_session.id)
        .all()
    )
    assert len(sf_snaps) == 1
    assert sf_snaps[0].status == "success"

    # SnapTrade account should be marked as failed
    st_acc = db.query(Account).filter_by(external_id="st_acc_001").first()
    assert st_acc.last_sync_status == "failed"

    # Log entries reflect both outcomes
    entries = (
        db.query(SyncLogEntry)
        .filter_by(sync_session_id=sync_session.id)
        .all()
    )
    entry_map = {e.provider_name: e for e in entries}
    assert entry_map["SnapTrade"].status == "failed"
    assert entry_map["SimpleFIN"].status == "success"
