"""Account management service."""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models import Account, AccountSnapshot, DailyHoldingValue, Security, SyncSession
from services.portfolio_valuation_service import PortfolioValuationService

logger = logging.getLogger(__name__)


class AccountService:
    """Service for managing account CRUD operations."""

    @staticmethod
    def list_accounts(db: Session) -> list[Account]:
        """List all accounts from the database."""
        return db.query(Account).all()

    @staticmethod
    def get_account(db: Session, account_id: str) -> Account | None:
        """Get a specific account by ID."""
        return db.query(Account).filter(Account.id == account_id).first()

    @staticmethod
    def update_account(
        db: Session,
        account_id: str,
        *,
        name: str | None = None,
        is_active: bool | None = None,
        assigned_asset_class_id: str | None = None,
    ) -> Account | None:
        """Update an account's properties."""
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return None

        if name is not None:
            account.name = name
            account.name_user_edited = True
        if is_active is not None:
            account.is_active = is_active
        if assigned_asset_class_id is not None:
            account.assigned_asset_class_id = assigned_asset_class_id

        db.commit()
        db.refresh(account)
        logger.info("Account updated: %s (id=%s)", account.name, account.id)
        return account

    @staticmethod
    def deactivate_account(
        db: Session,
        account_id: str,
        *,
        create_closing_snapshot: bool = True,
        superseded_by_account_id: str | None = None,
    ) -> Account | None:
        """Deactivate an account, optionally recording a closing $0 snapshot.

        The closing snapshot writes a zero-balance DailyHoldingValue for today
        so that historical portfolio charts show the account cleanly going to
        $0 on the deactivation date rather than abruptly vanishing.

        If the account already has $0 value (no current holdings), the closing
        snapshot is skipped regardless of create_closing_snapshot.

        Args:
            db: Database session
            account_id: ID of the account to deactivate
            create_closing_snapshot: If True, write a $0 closing snapshot
            superseded_by_account_id: Optional ID of the replacement account

        Returns:
            Updated Account, or None if not found
        """
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return None

        if not account.is_active:
            logger.info(
                "Account %s (%s) is already inactive, skipping deactivation",
                account.name, account_id,
            )
            return account

        today = date.today()
        now = datetime.now(timezone.utc)

        if create_closing_snapshot:
            # Check whether the account already has a zero-balance DHV for today
            # to avoid a duplicate sentinel.
            from utils.ticker import ZERO_BALANCE_TICKER
            already_zero = (
                db.query(DailyHoldingValue)
                .join(Security, DailyHoldingValue.security_id == Security.id)
                .filter(
                    DailyHoldingValue.account_id == account_id,
                    DailyHoldingValue.valuation_date == today,
                    Security.ticker == ZERO_BALANCE_TICKER,
                )
                .first()
            )

            if not already_zero:
                # Create a dedicated sync session for this closing snapshot
                closing_session = SyncSession(
                    timestamp=now,
                    is_complete=True,
                )
                db.add(closing_session)
                db.flush()

                # Create the $0 AccountSnapshot (no Holding children)
                closing_snapshot = AccountSnapshot(
                    account_id=account_id,
                    sync_session_id=closing_session.id,
                    status="success",
                    total_value=Decimal("0"),
                    balance_date=now,
                )
                db.add(closing_snapshot)
                db.flush()

                # Write the zero-balance sentinel DHV for today
                PortfolioValuationService.write_zero_balance_sentinel(
                    db, account_id, closing_snapshot.id, today
                )

                logger.info(
                    "Created closing snapshot for account %s (%s)",
                    account.name, account_id,
                )

        account.is_active = False
        account.deactivated_at = now
        if superseded_by_account_id is not None:
            account.superseded_by_account_id = superseded_by_account_id

        db.commit()
        db.refresh(account)
        logger.info(
            "Deactivated account %s (%s)%s",
            account.name,
            account_id,
            f", superseded by {superseded_by_account_id}" if superseded_by_account_id else "",
        )
        return account
