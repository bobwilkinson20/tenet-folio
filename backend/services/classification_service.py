"""Service for classifying holdings by asset type."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from models import Account, AssetClass, Security
from utils.ticker import ZERO_BALANCE_TICKER

# Type alias for (account_id, ticker) pairs used in batch classification
HoldingKey = tuple[str, str]

logger = logging.getLogger(__name__)


class ClassificationService:
    """Service for classifying holdings by asset type."""

    def get_holding_asset_type(
        self, db: Session, account_id: str, ticker: str
    ) -> Optional[AssetClass]:
        """
        Determine asset type for a holding using classification priority.

        Priority:
        1. Account-level override
        2. Security-level assignment
        3. None (unknown)

        Args:
            db: Database session
            account_id: Account ID
            ticker: Security ticker

        Returns:
            AssetClass if classified, None if unknown
        """
        # 1. Check account-level override
        account = db.query(Account).filter_by(id=account_id).first()
        if account and account.assigned_asset_class_id:
            return account.assigned_asset_class

        # 2. Check security-level assignment
        security = db.query(Security).filter_by(ticker=ticker).first()
        if security and security.manual_asset_class_id:
            return security.manual_asset_class

        # 3. Unknown
        return None

    def classify_holdings_batch(
        self,
        db: Session,
        holdings: list[HoldingKey],
    ) -> dict[HoldingKey, Optional[AssetClass]]:
        """
        Classify multiple holdings in bulk (2 queries total).

        Args:
            db: Database session
            holdings: List of (account_id, ticker) tuples

        Returns:
            Dict mapping (account_id, ticker) to AssetClass or None
        """
        if not holdings:
            return {}

        account_ids = {account_id for account_id, _ in holdings}
        tickers = {ticker for _, ticker in holdings}

        # Bulk-fetch accounts with their assigned asset classes (1 query)
        accounts = (
            db.query(Account)
            .options(joinedload(Account.assigned_asset_class))
            .filter(Account.id.in_(account_ids))
            .all()
        )
        account_map = {a.id: a for a in accounts}

        # Bulk-fetch securities with their manual asset classes (1 query)
        securities = (
            db.query(Security)
            .options(joinedload(Security.manual_asset_class))
            .filter(Security.ticker.in_(tickers))
            .all()
        )
        security_map = {s.ticker: s for s in securities}

        # Apply classification waterfall in-memory
        result: dict[HoldingKey, Optional[AssetClass]] = {}
        for account_id, ticker in holdings:
            # 1. Account override
            account = account_map.get(account_id)
            if account and account.assigned_asset_class_id:
                result[(account_id, ticker)] = account.assigned_asset_class
                continue

            # 2. Security assignment
            security = security_map.get(ticker)
            if security and security.manual_asset_class_id:
                result[(account_id, ticker)] = security.manual_asset_class
                continue

            # 3. Unknown
            result[(account_id, ticker)] = None

        return result

    def count_unassigned_securities(self, db: Session) -> int:
        """
        Count securities that don't have an asset type assignment.

        Note: This counts securities that exist in the database,
        not holdings that may be assigned via account override.

        Args:
            db: Database session

        Returns:
            Count of unassigned securities
        """
        return (
            db.query(Security)
            .filter(
                Security.manual_asset_class_id.is_(None),
                Security.ticker != ZERO_BALANCE_TICKER,
            )
            .count()
        )
