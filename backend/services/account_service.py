"""Account management service."""

import logging

from sqlalchemy.orm import Session

from models import Account

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
