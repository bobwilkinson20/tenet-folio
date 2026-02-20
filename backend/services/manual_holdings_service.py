"""Service for managing manually created accounts and their holdings."""

import hashlib
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import Account, AccountSnapshot, Holding, Security, SyncSession
from models.holding_lot import HoldingLot
from schemas import ManualHoldingInput
from services.portfolio_valuation_service import PortfolioValuationService
from services.security_service import SecurityService

logger = logging.getLogger(__name__)


MANUAL_PROVIDER_NAME = "Manual"


def generate_manual_synthetic_ticker(description: str, unique_id: str) -> str:
    """Generate a synthetic ticker for a description-based holding.

    Format: _MAN:{12-hex-chars} (SHA256 of description:unique_id)
    """
    raw = f"{description}:{unique_id}"
    hex_hash = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"_MAN:{hex_hash}"


class ManualHoldingsService:
    """Service for CRUD operations on manual account holdings."""

    @staticmethod
    def create_manual_account(
        db: Session,
        name: str,
        institution_name: Optional[str] = None,
    ) -> Account:
        """Create a new manual account.

        Args:
            db: Database session
            name: Account display name
            institution_name: Optional institution name

        Returns:
            The created Account
        """
        account = Account(
            provider_name=MANUAL_PROVIDER_NAME,
            external_id=str(uuid.uuid4()),
            name=name,
            institution_name=institution_name,
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        logger.info("Manual account created: %s (id=%s)", name, account.id)
        return account

    @staticmethod
    def is_manual_account(account: Account) -> bool:
        """Check whether an account is manually managed."""
        return account.provider_name == MANUAL_PROVIDER_NAME

    @staticmethod
    def get_current_holdings(db: Session, account_id: str) -> list[Holding]:
        """Get the current holdings for a manual account.

        Returns holdings from the latest snapshot, or empty list if none.
        """
        latest_acct_snap = (
            db.query(AccountSnapshot)
            .join(SyncSession)
            .filter(AccountSnapshot.account_id == account_id)
            .order_by(SyncSession.timestamp.desc())
            .limit(1)
            .first()
        )

        if latest_acct_snap is None:
            return []

        return (
            db.query(Holding)
            .filter(Holding.account_snapshot_id == latest_acct_snap.id)
            .all()
        )

    @staticmethod
    def _create_sync_session_with_holdings(
        db: Session,
        account_id: str,
        holdings_data: list[dict],
    ) -> SyncSession:
        """Create a new sync session with the given holdings.

        Args:
            db: Database session
            account_id: The account ID
            holdings_data: List of dicts with ticker, quantity, price, market_value

        Returns:
            The created SyncSession
        """
        sync_session = SyncSession(is_complete=True)
        db.add(sync_session)
        db.flush()

        # Calculate total value first
        total_value = sum(h["market_value"] for h in holdings_data)
        now = datetime.now(timezone.utc)

        # Create AccountSnapshot BEFORE holdings (so holdings can reference it)
        account_snapshot = AccountSnapshot(
            account_id=account_id,
            sync_session_id=sync_session.id,
            status="success",
            total_value=total_value,
            balance_date=now,
        )
        db.add(account_snapshot)
        db.flush()  # Get the account_snapshot ID

        # Update balance_date on the Account itself
        account = db.query(Account).filter(Account.id == account_id).first()
        if account:
            account.balance_date = now

        created_holdings = []
        for h_data in holdings_data:
            security = SecurityService.ensure_exists(
                db,
                h_data["ticker"],
                name=h_data.get("description"),
                update_name=h_data["ticker"].startswith("_MAN:"),
            )

            holding = Holding(
                account_snapshot_id=account_snapshot.id,
                security_id=security.id,
                ticker=h_data["ticker"],
                quantity=h_data.get("quantity", Decimal("0")),
                snapshot_price=h_data.get("price", Decimal("0")),
                snapshot_value=h_data["market_value"],
            )
            db.add(holding)
            created_holdings.append(holding)

        # Create DailyHoldingValue rows for today
        if created_holdings:
            db.flush()
            PortfolioValuationService.create_daily_values_for_holdings(
                db, created_holdings, date.today(), account_id=account_id
            )
            PortfolioValuationService.delete_zero_balance_sentinel(
                db, account_id, date.today()
            )
        else:
            PortfolioValuationService.write_zero_balance_sentinel(
                db, account_id, account_snapshot.id, date.today()
            )

        db.commit()
        db.refresh(sync_session)
        for h in created_holdings:
            db.refresh(h)

        return sync_session

    @staticmethod
    def _holding_to_dict(holding: Holding, db: Optional[Session] = None) -> dict:
        """Convert a Holding ORM object to a dict for snapshot creation."""
        result = {
            "ticker": holding.ticker,
            "quantity": holding.quantity,
            "price": holding.snapshot_price,
            "market_value": holding.snapshot_value,
        }
        # Preserve description for _MAN: holdings so Security.name stays current
        if holding.ticker.startswith("_MAN:") and db is not None:
            security = db.query(Security).filter_by(ticker=holding.ticker).first()
            if security:
                result["description"] = security.name
        return result

    @staticmethod
    def _input_to_dict(
        holding_input: ManualHoldingInput,
        existing_ticker: Optional[str] = None,
    ) -> dict:
        """Convert a ManualHoldingInput to a dict for snapshot creation.

        Args:
            holding_input: The input from the API
            existing_ticker: For Other-mode edits, reuse the existing _MAN: ticker
        """
        if holding_input.description:
            # Other mode: generate synthetic ticker or reuse existing
            ticker = existing_ticker or generate_manual_synthetic_ticker(
                holding_input.description, str(uuid.uuid4())
            )
            return {
                "ticker": ticker,
                "quantity": Decimal("1"),
                "price": holding_input.market_value,
                "market_value": holding_input.market_value,
                "description": holding_input.description,
            }
        return {
            "ticker": holding_input.ticker,
            "quantity": holding_input.quantity,
            "price": holding_input.price or Decimal("0"),
            "market_value": holding_input.market_value,
        }

    @staticmethod
    def _find_existing_manual_ticker(
        db: Session,
        description: str,
        current_tickers: set[str],
    ) -> Optional[str]:
        """Find an existing _MAN: Security whose name matches the description.

        Reusing the ticker preserves asset classification history when a
        holding is deleted and later re-added with the same description.

        Returns the ticker if found and not already in current holdings,
        else None.
        """
        existing = (
            db.query(Security)
            .filter(
                Security.ticker.startswith("_MAN:"),
                Security.name == description,
            )
            .first()
        )
        if existing and existing.ticker not in current_tickers:
            return existing.ticker
        return None

    @staticmethod
    def add_holding(
        db: Session,
        account: Account,
        holding_input: ManualHoldingInput,
    ) -> Holding:
        """Add a holding to a manual account.

        Creates a new sync session with all existing holdings plus the new one.

        Returns:
            The newly created Holding record
        """
        # Acquire the SQLite write lock up front so the entire
        # read-modify-write cycle is atomic.  BEGIN IMMEDIATE prevents
        # a concurrent writer from inserting a snapshot between the
        # read of current holdings and the creation of the new one.
        db.execute(text("BEGIN IMMEDIATE"))
        current = ManualHoldingsService.get_current_holdings(db, account.id)
        holdings_data = [ManualHoldingsService._holding_to_dict(h, db) for h in current]

        # For Other mode, reuse an existing _MAN: ticker with the same
        # description to preserve asset classification history.
        reuse_ticker = None
        if holding_input.description:
            current_tickers = {h.ticker for h in current}
            reuse_ticker = ManualHoldingsService._find_existing_manual_ticker(
                db, holding_input.description.strip(), current_tickers
            )

        new_data = ManualHoldingsService._input_to_dict(
            holding_input, existing_ticker=reuse_ticker
        )
        holdings_data.append(new_data)

        sync_session = ManualHoldingsService._create_sync_session_with_holdings(
            db, account.id, holdings_data
        )

        ticker = new_data["ticker"]
        acct_snap = (
            db.query(AccountSnapshot)
            .filter(
                AccountSnapshot.sync_session_id == sync_session.id,
                AccountSnapshot.account_id == account.id,
            )
            .first()
        )
        new_holding = (
            db.query(Holding)
            .filter(
                Holding.account_snapshot_id == acct_snap.id,
                Holding.ticker == ticker,
            )
            .order_by(Holding.created_at.desc())
            .first()
        )

        # Create a HoldingLot for cost basis tracking
        # Other mode always uses qty 1; security mode has validated quantity > 0
        if holding_input.description:
            lot_quantity = Decimal("1")
        else:
            lot_quantity = holding_input.quantity

        lot_cost = (
            holding_input.cost_basis_per_unit
            if holding_input.cost_basis_per_unit is not None
            else (new_holding.snapshot_price or Decimal("0"))
        )

        lot = HoldingLot(
            account_id=account.id,
            security_id=new_holding.security_id,
            ticker=ticker,
            acquisition_date=holding_input.acquisition_date,
            cost_basis_per_unit=lot_cost,
            original_quantity=lot_quantity,
            current_quantity=lot_quantity,
            source="manual",
        )
        db.add(lot)
        db.commit()

        logger.info(
            "Holding added to %s: %s (session %s)",
            account.name, ticker, sync_session.id[:8],
        )
        return new_holding

    @staticmethod
    def update_holding(
        db: Session,
        account: Account,
        holding_id: str,
        holding_input: ManualHoldingInput,
    ) -> Holding:
        """Update a holding on a manual account.

        Creates a new sync session with the target holding replaced.

        Raises:
            ValueError: If holding_id is not found in current holdings
        """
        # Acquire the SQLite write lock for the read-modify-write cycle.
        db.execute(text("BEGIN IMMEDIATE"))
        current = ManualHoldingsService.get_current_holdings(db, account.id)

        found = False
        updated_ticker = None
        holdings_data = []
        for h in current:
            if h.id == holding_id:
                found = True
                # For Other mode edits, reuse the existing _MAN: ticker
                existing_ticker = h.ticker if h.ticker.startswith("_MAN:") else None
                data = ManualHoldingsService._input_to_dict(
                    holding_input, existing_ticker=existing_ticker
                )
                updated_ticker = data["ticker"]
                holdings_data.append(data)
            else:
                holdings_data.append(ManualHoldingsService._holding_to_dict(h, db))

        if not found:
            raise ValueError(f"Holding {holding_id} not found")

        sync_session = ManualHoldingsService._create_sync_session_with_holdings(
            db, account.id, holdings_data
        )

        # Return the updated holding
        acct_snap = (
            db.query(AccountSnapshot)
            .filter(
                AccountSnapshot.sync_session_id == sync_session.id,
                AccountSnapshot.account_id == account.id,
            )
            .first()
        )
        updated_holding = (
            db.query(Holding)
            .filter(
                Holding.account_snapshot_id == acct_snap.id,
                Holding.ticker == updated_ticker,
            )
            .first()
        )
        logger.info(
            "Holding updated in %s: %s (session %s)",
            account.name, updated_ticker, sync_session.id[:8],
        )
        return updated_holding

    @staticmethod
    def delete_holding(
        db: Session,
        account: Account,
        holding_id: str,
    ) -> None:
        """Delete a holding from a manual account.

        Creates a new sync session without the target holding.

        Raises:
            ValueError: If holding_id is not found in current holdings
        """
        # Acquire the SQLite write lock for the read-modify-write cycle.
        db.execute(text("BEGIN IMMEDIATE"))
        current = ManualHoldingsService.get_current_holdings(db, account.id)

        found = False
        holdings_data = []
        for h in current:
            if h.id == holding_id:
                found = True
            else:
                holdings_data.append(ManualHoldingsService._holding_to_dict(h, db))

        if not found:
            raise ValueError(f"Holding {holding_id} not found")

        sync_session = ManualHoldingsService._create_sync_session_with_holdings(
            db, account.id, holdings_data
        )
        logger.info(
            "Holding deleted from %s: %s (session %s)",
            account.name, holding_id, sync_session.id[:8],
        )
