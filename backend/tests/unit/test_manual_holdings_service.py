"""Unit tests for ManualHoldingsService."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from models import AccountSnapshot, DailyHoldingValue, Security, SyncSession
from models.holding_lot import HoldingLot
from schemas import ManualHoldingInput
from services.manual_holdings_service import (
    ManualHoldingsService,
    generate_manual_synthetic_ticker,
)


class TestCreateManualAccount:
    def test_create_manual_account(self, db):
        account = ManualHoldingsService.create_manual_account(db, "My House")

        assert account.provider_name == "Manual"
        assert account.name == "My House"
        assert account.institution_name is None
        assert account.is_active is True
        # external_id should be a valid UUID string
        assert len(account.external_id) == 36
        assert "-" in account.external_id

    def test_create_manual_account_with_institution(self, db):
        account = ManualHoldingsService.create_manual_account(
            db, "Savings", institution_name="Local Bank"
        )
        assert account.institution_name == "Local Bank"


class TestIsManualAccount:
    def test_is_manual_account_true(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Manual")
        assert ManualHoldingsService.is_manual_account(account) is True

    def test_is_manual_account_false(self, db, account):
        assert ManualHoldingsService.is_manual_account(account) is False


class TestAddHolding:
    def test_add_holding_to_empty_account(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")

        holding_input = ManualHoldingInput(
            ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")
        )
        holding = ManualHoldingsService.add_holding(db, account, holding_input)

        assert holding.ticker == "HOME"
        assert holding.snapshot_value == Decimal("500000")
        assert holding.account_snapshot_id is not None

        # Verify sync session and account_snapshot were created
        sync_sessions = db.query(SyncSession).all()
        assert len(sync_sessions) == 1
        assert sync_sessions[0].is_complete is True

        acct_snaps = db.query(AccountSnapshot).filter_by(account_id=account.id).all()
        assert len(acct_snaps) == 1
        assert acct_snaps[0].total_value == Decimal("500000")

    def test_add_holding_sets_balance_date(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")
        assert account.balance_date is None

        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )

        db.refresh(account)
        assert account.balance_date is not None

        # AccountSnapshot should also have balance_date set
        acct_snap = (
            db.query(AccountSnapshot)
            .filter(AccountSnapshot.account_id == account.id)
            .first()
        )
        assert acct_snap.balance_date is not None

    def test_add_holding_preserves_existing(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")

        # Add first holding
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )

        # Add second holding
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="CAR", quantity=Decimal("1"), market_value=Decimal("30000")),
        )

        # Get current holdings — should have both
        current = ManualHoldingsService.get_current_holdings(db, account.id)
        tickers = {h.ticker for h in current}
        assert tickers == {"HOME", "CAR"}

        # Latest account snapshot should have combined total
        acct_snap = (
            db.query(AccountSnapshot)
            .join(SyncSession)
            .filter(AccountSnapshot.account_id == account.id)
            .order_by(SyncSession.timestamp.desc())
            .first()
        )
        assert acct_snap.total_value == Decimal("530000")


class TestUpdateHolding:
    def test_update_holding(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")

        # Add two holdings
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )

        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="CAR", quantity=Decimal("1"), market_value=Decimal("30000")),
        )

        # Need to get the holding_id from the latest sync session
        current = ManualHoldingsService.get_current_holdings(db, account.id)
        home_holding = [h for h in current if h.ticker == "HOME"][0]

        # Update HOME value
        updated = ManualHoldingsService.update_holding(
            db, account, home_holding.id,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("520000")),
        )

        assert updated.ticker == "HOME"
        assert updated.snapshot_value == Decimal("520000")

        # CAR should still be there
        current = ManualHoldingsService.get_current_holdings(db, account.id)
        tickers = {h.ticker: h.snapshot_value for h in current}
        assert tickers["HOME"] == Decimal("520000")
        assert tickers["CAR"] == Decimal("30000")

    def test_update_holding_not_found(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )

        with pytest.raises(ValueError, match="not found"):
            ManualHoldingsService.update_holding(
                db, account, "nonexistent-id",
                ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("520000")),
            )


class TestDeleteHolding:
    def test_delete_holding(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")

        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="CAR", quantity=Decimal("1"), market_value=Decimal("30000")),
        )

        current = ManualHoldingsService.get_current_holdings(db, account.id)
        home_holding = [h for h in current if h.ticker == "HOME"][0]

        ManualHoldingsService.delete_holding(db, account, home_holding.id)

        current = ManualHoldingsService.get_current_holdings(db, account.id)
        assert len(current) == 1
        assert current[0].ticker == "CAR"

    def test_delete_holding_not_found(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )

        with pytest.raises(ValueError, match="not found"):
            ManualHoldingsService.delete_holding(db, account, "nonexistent-id")

    def test_delete_last_holding(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )

        current = ManualHoldingsService.get_current_holdings(db, account.id)
        ManualHoldingsService.delete_holding(db, account, current[0].id)

        current = ManualHoldingsService.get_current_holdings(db, account.id)
        assert len(current) == 0

        # SyncSession should still exist with zero total
        acct_snap = (
            db.query(AccountSnapshot)
            .join(SyncSession)
            .filter(AccountSnapshot.account_id == account.id)
            .order_by(SyncSession.timestamp.desc())
            .first()
        )
        assert acct_snap.total_value == Decimal("0")


class TestSecurityCreation:
    def test_add_holding_creates_security_record(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )

        security = db.query(Security).filter_by(ticker="HOME").first()
        assert security is not None
        assert security.ticker == "HOME"


class TestMarketValueValidation:
    def test_market_value_auto_calculated(self):
        h = ManualHoldingInput(
            ticker="AAPL", quantity=Decimal("10"), price=Decimal("150")
        )
        assert h.market_value == Decimal("1500")

    def test_quantity_required_for_security_mode(self):
        with pytest.raises(ValidationError, match="quantity is required"):
            ManualHoldingInput(ticker="AAPL", market_value=Decimal("1500"))

    def test_zero_quantity_rejected(self):
        """Zero quantity is rejected for security holdings."""
        with pytest.raises(ValidationError, match="quantity is required"):
            ManualHoldingInput(
                ticker="HOME", quantity=Decimal("0"), market_value=Decimal("500000")
            )

    def test_market_value_explicit(self):
        h = ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000"))
        assert h.market_value == Decimal("500000")
        assert h.quantity == Decimal("1")
        assert h.price is None

    def test_zero_market_value_allowed(self):
        """Zero market value is valid (e.g. worthless stock)."""
        h = ManualHoldingInput(
            ticker="DEAD", quantity=Decimal("1"), market_value=Decimal("0")
        )
        assert h.market_value == Decimal("0")

    def test_negative_market_value_allowed(self):
        """Negative market value is valid (e.g. mortgage liability)."""
        h = ManualHoldingInput(
            description="Mortgage", market_value=Decimal("-350000")
        )
        assert h.market_value == Decimal("-350000")


class TestHistoryPreserved:
    def test_history_preserved(self, db):
        """Multiple edits create separate sync sessions with correct data."""
        account = ManualHoldingsService.create_manual_account(db, "Test")

        # Add a holding
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )

        # Update the holding
        current = ManualHoldingsService.get_current_holdings(db, account.id)
        ManualHoldingsService.update_holding(
            db, account, current[0].id,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("520000")),
        )

        # Delete the holding
        current = ManualHoldingsService.get_current_holdings(db, account.id)
        ManualHoldingsService.delete_holding(db, account, current[0].id)

        # Should have 3 sync sessions total (add, update, delete)
        acct_snaps = (
            db.query(AccountSnapshot)
            .join(SyncSession)
            .filter(AccountSnapshot.account_id == account.id)
            .order_by(SyncSession.timestamp.asc())
            .all()
        )
        assert len(acct_snaps) == 3
        assert acct_snaps[0].total_value == Decimal("500000")
        assert acct_snaps[1].total_value == Decimal("520000")
        assert acct_snaps[2].total_value == Decimal("0")


class TestManualHoldingInputValidation:
    def test_description_with_market_value_succeeds(self):
        h = ManualHoldingInput(
            description="Primary Residence", market_value=Decimal("500000")
        )
        assert h.description == "Primary Residence"
        assert h.market_value == Decimal("500000")
        assert h.ticker is None

    def test_description_without_market_value_fails(self):
        with pytest.raises(ValidationError, match="market_value is required"):
            ManualHoldingInput(description="Primary Residence")

    def test_both_ticker_and_description_fails(self):
        with pytest.raises(ValidationError, match="not both"):
            ManualHoldingInput(
                ticker="HOME",
                description="Primary Residence",
                market_value=Decimal("500000"),
            )

    def test_neither_ticker_nor_description_fails(self):
        with pytest.raises(ValidationError, match="Either ticker or description"):
            ManualHoldingInput(market_value=Decimal("500000"))

    def test_security_mode_with_quantity(self):
        h = ManualHoldingInput(
            ticker="AAPL", quantity=Decimal("10"), market_value=Decimal("1500")
        )
        assert h.ticker == "AAPL"
        assert h.quantity == Decimal("10")
        assert h.description is None


class TestSyntheticTickerGeneration:
    def test_man_prefix(self):
        ticker = generate_manual_synthetic_ticker("Test", "abc")
        assert ticker.startswith("_MAN:")

    def test_length(self):
        ticker = generate_manual_synthetic_ticker("Test", "abc")
        # _MAN: (5 chars) + 12 hex chars = 17 total
        assert len(ticker) == 17

    def test_uniqueness(self):
        t1 = generate_manual_synthetic_ticker("Test", "id-1")
        t2 = generate_manual_synthetic_ticker("Test", "id-2")
        assert t1 != t2


class TestOtherModeHoldings:
    def test_add_other_holding_creates_man_ticker(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")
        holding_input = ManualHoldingInput(
            description="Primary Residence", market_value=Decimal("500000")
        )
        holding = ManualHoldingsService.add_holding(db, account, holding_input)

        assert holding.ticker.startswith("_MAN:")
        assert holding.snapshot_value == Decimal("500000")
        assert holding.quantity == Decimal("1")

    def test_add_other_holding_stores_description_as_security_name(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")
        holding_input = ManualHoldingInput(
            description="Primary Residence", market_value=Decimal("500000")
        )
        holding = ManualHoldingsService.add_holding(db, account, holding_input)

        security = db.query(Security).filter_by(ticker=holding.ticker).first()
        assert security is not None
        assert security.name == "Primary Residence"

    def test_update_other_holding_preserves_ticker(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")
        holding_input = ManualHoldingInput(
            description="Primary Residence", market_value=Decimal("500000")
        )
        holding = ManualHoldingsService.add_holding(db, account, holding_input)
        original_ticker = holding.ticker

        # Update value
        current = ManualHoldingsService.get_current_holdings(db, account.id)
        man_holding = [h for h in current if h.ticker.startswith("_MAN:")][0]

        updated = ManualHoldingsService.update_holding(
            db, account, man_holding.id,
            ManualHoldingInput(description="Primary Residence", market_value=Decimal("520000")),
        )

        assert updated.ticker == original_ticker
        assert updated.snapshot_value == Decimal("520000")

    def test_update_other_holding_updates_security_name(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")
        holding = ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(description="My House", market_value=Decimal("500000")),
        )
        ticker = holding.ticker

        current = ManualHoldingsService.get_current_holdings(db, account.id)
        man_holding = [h for h in current if h.ticker.startswith("_MAN:")][0]

        ManualHoldingsService.update_holding(
            db, account, man_holding.id,
            ManualHoldingInput(description="Primary Residence", market_value=Decimal("520000")),
        )

        security = db.query(Security).filter_by(ticker=ticker).first()
        assert security.name == "Primary Residence"

    def test_delete_other_holding(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(description="Primary Residence", market_value=Decimal("500000")),
        )

        current = ManualHoldingsService.get_current_holdings(db, account.id)
        assert len(current) == 1

        ManualHoldingsService.delete_holding(db, account, current[0].id)

        current = ManualHoldingsService.get_current_holdings(db, account.id)
        assert len(current) == 0

    def test_mixed_security_and_other_coexist(self, db):
        account = ManualHoldingsService.create_manual_account(db, "Test")

        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="VTI", quantity=Decimal("100"), price=Decimal("250")),
        )
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(description="Primary Residence", market_value=Decimal("500000")),
        )

        current = ManualHoldingsService.get_current_holdings(db, account.id)
        assert len(current) == 2

        tickers = {h.ticker for h in current}
        assert "VTI" in tickers
        assert any(t.startswith("_MAN:") for t in tickers)

    def test_readd_reuses_ticker_after_delete(self, db):
        """Deleting and re-adding with the same description reuses the ticker."""
        account = ManualHoldingsService.create_manual_account(db, "Test")

        # Add, then delete
        holding = ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(description="Primary Residence", market_value=Decimal("500000")),
        )
        original_ticker = holding.ticker

        current = ManualHoldingsService.get_current_holdings(db, account.id)
        ManualHoldingsService.delete_holding(db, account, current[0].id)

        # Re-add with same description
        holding2 = ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(description="Primary Residence", market_value=Decimal("520000")),
        )

        assert holding2.ticker == original_ticker

    def test_readd_different_description_gets_new_ticker(self, db):
        """A different description should get a new ticker, not reuse."""
        account = ManualHoldingsService.create_manual_account(db, "Test")

        holding = ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(description="Primary Residence", market_value=Decimal("500000")),
        )
        original_ticker = holding.ticker

        current = ManualHoldingsService.get_current_holdings(db, account.id)
        ManualHoldingsService.delete_holding(db, account, current[0].id)

        # Add with a different description
        holding2 = ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(description="Vacation Home", market_value=Decimal("300000")),
        )

        assert holding2.ticker != original_ticker

    def test_duplicate_description_gets_new_ticker(self, db):
        """Adding a second holding with the same description gets a new ticker."""
        account = ManualHoldingsService.create_manual_account(db, "Test")

        holding1 = ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(description="Art Piece", market_value=Decimal("10000")),
        )

        holding2 = ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(description="Art Piece", market_value=Decimal("20000")),
        )

        # Both exist but have different tickers
        assert holding1.ticker != holding2.ticker
        current = ManualHoldingsService.get_current_holdings(db, account.id)
        assert len(current) == 2


class TestManualHoldingsCreateDailyValues:
    """Tests that manual holding operations create DailyHoldingValue rows."""

    def test_add_holding_creates_daily_values(self, db):
        """Adding a holding should create DailyHoldingValue rows."""
        account = ManualHoldingsService.create_manual_account(db, "Test")

        holding_input = ManualHoldingInput(
            ticker="HOME", market_value=Decimal("500000"),
            price=Decimal("500000"), quantity=Decimal("1"),
        )
        ManualHoldingsService.add_holding(db, account, holding_input)

        dhv_rows = db.query(DailyHoldingValue).all()
        assert len(dhv_rows) == 1
        assert dhv_rows[0].market_value == Decimal("500000")
        assert dhv_rows[0].close_price == Decimal("500000")

    def test_update_holding_creates_daily_values_for_new_snapshot(self, db):
        """Updating a holding creates DailyHoldingValue for the replacement snapshot."""
        account = ManualHoldingsService.create_manual_account(db, "Test")

        holding_input = ManualHoldingInput(
            ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000"),
        )
        holding = ManualHoldingsService.add_holding(db, account, holding_input)

        # Update the holding
        update_input = ManualHoldingInput(
            ticker="HOME", quantity=Decimal("1"), market_value=Decimal("520000"),
        )
        ManualHoldingsService.update_holding(db, account, holding.id, update_input)

        # With account_id-based upsert, the update overwrites the original DHV row
        # (same date + account + security = upsert instead of new row)
        dhv_rows = db.query(DailyHoldingValue).all()
        assert len(dhv_rows) == 1
        assert dhv_rows[0].market_value == Decimal("520000")


class TestManualHoldingLotCreation:
    def test_add_holding_creates_lot_with_defaults(self, db):
        """Adding a holding without cost basis fields creates a lot with snapshot_price."""
        account = ManualHoldingsService.create_manual_account(db, "Test")
        holding_input = ManualHoldingInput(
            ticker="AAPL",
            quantity=Decimal("10"),
            price=Decimal("150"),
        )
        holding = ManualHoldingsService.add_holding(db, account, holding_input)

        lots = db.query(HoldingLot).filter_by(account_id=account.id).all()
        assert len(lots) == 1
        lot = lots[0]
        assert lot.ticker == "AAPL"
        assert lot.original_quantity == Decimal("10")
        assert lot.current_quantity == Decimal("10")
        assert lot.cost_basis_per_unit == holding.snapshot_price
        assert lot.acquisition_date is None
        assert lot.source == "manual"
        assert lot.security_id == holding.security_id

    def test_add_holding_creates_lot_with_cost_basis(self, db):
        """Adding a holding with explicit cost basis fields uses provided values."""
        account = ManualHoldingsService.create_manual_account(db, "Test")
        holding_input = ManualHoldingInput(
            ticker="AAPL",
            quantity=Decimal("10"),
            price=Decimal("150"),
            acquisition_date=date(2024, 1, 15),
            cost_basis_per_unit=Decimal("120"),
        )
        holding = ManualHoldingsService.add_holding(db, account, holding_input)

        lots = db.query(HoldingLot).filter_by(account_id=account.id).all()
        assert len(lots) == 1
        lot = lots[0]
        assert lot.acquisition_date == date(2024, 1, 15)
        assert lot.cost_basis_per_unit == Decimal("120")
        assert lot.original_quantity == Decimal("10")
        assert lot.security_id == holding.security_id

    def test_add_holding_other_mode_lot_qty_1(self, db):
        """Other-mode holding creates lot with quantity=1 and cost=market_value."""
        account = ManualHoldingsService.create_manual_account(db, "Test")
        holding_input = ManualHoldingInput(
            description="Primary Residence",
            market_value=Decimal("500000"),
        )
        ManualHoldingsService.add_holding(db, account, holding_input)

        lots = db.query(HoldingLot).filter_by(account_id=account.id).all()
        assert len(lots) == 1
        lot = lots[0]
        assert lot.original_quantity == Decimal("1")
        assert lot.current_quantity == Decimal("1")
        # In other mode, snapshot_price is set to market_value
        assert lot.cost_basis_per_unit == Decimal("500000")

    def test_add_holding_with_only_acquisition_date(self, db):
        """Providing only acquisition_date uses snapshot_price for cost basis."""
        account = ManualHoldingsService.create_manual_account(db, "Test")
        holding_input = ManualHoldingInput(
            ticker="VTI",
            quantity=Decimal("50"),
            price=Decimal("200"),
            acquisition_date=date(2023, 6, 1),
        )
        holding = ManualHoldingsService.add_holding(db, account, holding_input)

        lots = db.query(HoldingLot).filter_by(account_id=account.id).all()
        assert len(lots) == 1
        lot = lots[0]
        assert lot.acquisition_date == date(2023, 6, 1)
        assert lot.cost_basis_per_unit == holding.snapshot_price


class TestManualHoldingsSentinel:
    """Tests for sentinel DHV rows when manual account has zero holdings."""

    def test_delete_last_holding_writes_sentinel(self, db):
        """Deleting the last holding writes a _ZERO_BALANCE sentinel DHV."""
        from utils.ticker import ZERO_BALANCE_TICKER

        account = ManualHoldingsService.create_manual_account(db, "Test")
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )

        # Should have a real DHV row
        real_rows = db.query(DailyHoldingValue).filter(
            DailyHoldingValue.ticker == "HOME"
        ).count()
        assert real_rows == 1

        # Delete the holding
        current = ManualHoldingsService.get_current_holdings(db, account.id)
        ManualHoldingsService.delete_holding(db, account, current[0].id)

        # Should have sentinel, no real rows
        dhv_rows = db.query(DailyHoldingValue).filter(
            DailyHoldingValue.account_id == account.id
        ).all()
        assert len(dhv_rows) == 1
        assert dhv_rows[0].ticker == ZERO_BALANCE_TICKER
        assert dhv_rows[0].market_value == Decimal("0")

    def test_add_holding_to_empty_account_deletes_sentinel(self, db):
        """Adding a holding to an empty account deletes the sentinel DHV."""
        from utils.ticker import ZERO_BALANCE_TICKER

        account = ManualHoldingsService.create_manual_account(db, "Test")

        # Add and then delete to create sentinel state
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="HOME", quantity=Decimal("1"), market_value=Decimal("500000")),
        )
        current = ManualHoldingsService.get_current_holdings(db, account.id)
        ManualHoldingsService.delete_holding(db, account, current[0].id)

        # Verify sentinel exists
        sentinel_rows = db.query(DailyHoldingValue).filter(
            DailyHoldingValue.ticker == ZERO_BALANCE_TICKER,
            DailyHoldingValue.account_id == account.id,
        ).count()
        assert sentinel_rows == 1

        # Add a new holding
        ManualHoldingsService.add_holding(
            db, account,
            ManualHoldingInput(ticker="CAR", quantity=Decimal("1"), market_value=Decimal("30000")),
        )

        # Sentinel should be gone, real DHV should exist
        sentinel_rows = db.query(DailyHoldingValue).filter(
            DailyHoldingValue.ticker == ZERO_BALANCE_TICKER,
            DailyHoldingValue.account_id == account.id,
        ).count()
        assert sentinel_rows == 0

        real_rows = db.query(DailyHoldingValue).filter(
            DailyHoldingValue.ticker == "CAR",
            DailyHoldingValue.account_id == account.id,
        ).count()
        assert real_rows == 1
