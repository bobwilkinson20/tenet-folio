"""Activity service - handles persisting and deduplicating activities."""

import json
import logging

from sqlalchemy.orm import Session

from integrations.provider_protocol import ProviderActivity
from models import Account
from models.activity import Activity

logger = logging.getLogger(__name__)


class ActivityService:
    """Service for syncing activity/transaction data from providers."""

    @staticmethod
    def sync_activities(
        db: Session,
        provider_name: str,
        account: Account,
        provider_activities: list[ProviderActivity],
    ) -> int:
        """Persist activities with deduplication.

        Uses an in-memory set of existing external_ids for the account
        to efficiently skip duplicates.

        Args:
            db: Database session.
            provider_name: Name of the provider (e.g., "SnapTrade").
            account: The Account record to associate activities with.
            provider_activities: List of activities from the provider.

        Returns:
            Count of new activities inserted.
        """
        if not provider_activities:
            return 0

        # Load existing external_ids for this account+provider in one query
        existing_ids = set(
            row[0]
            for row in db.query(Activity.external_id)
            .filter(
                Activity.account_id == account.id,
                Activity.provider_name == provider_name,
            )
            .all()
        )

        new_count = 0
        for pa in provider_activities:
            if pa.external_id in existing_ids:
                continue

            raw_data_str = None
            if pa.raw_data is not None:
                try:
                    raw_data_str = json.dumps(pa.raw_data, default=str)
                except (TypeError, ValueError):
                    raw_data_str = str(pa.raw_data)

            activity = Activity(
                account_id=account.id,
                provider_name=provider_name,
                external_id=pa.external_id,
                activity_date=pa.activity_date,
                settlement_date=pa.settlement_date,
                type=pa.type,
                description=pa.description,
                ticker=pa.ticker,
                units=pa.units,
                price=pa.price,
                amount=pa.amount,
                currency=pa.currency,
                fee=pa.fee,
                raw_data=raw_data_str,
            )
            db.add(activity)
            existing_ids.add(pa.external_id)
            new_count += 1

        skipped = len(provider_activities) - new_count
        if new_count > 0 or skipped > 0:
            logger.info(
                "Activities for %s: %d new, %d duplicates skipped",
                account.name, new_count, skipped,
            )

        return new_count
