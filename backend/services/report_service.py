"""Service for generating portfolio report data."""

import logging
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from models import Account
from services.classification_service import ClassificationService
from services.portfolio_service import PortfolioService
from utils.ticker import ZERO_BALANCE_TICKER

logger = logging.getLogger(__name__)


def generate_account_asset_class_rows(
    db: Session, allocation_only: bool = False
) -> list[list[str]]:
    """Generate report rows grouped by (account, asset class).

    Each row is ``[account_name, asset_class_name, market_value]``.
    Account names appear only on the first row for that account;
    subsequent rows use ``/`` as a continuation marker.

    Args:
        db: Database session.
        allocation_only: If True, include only allocation-flagged accounts.

    Returns:
        List of 3-element string lists ready for Google Sheets.
    """
    holdings = PortfolioService().get_current_holdings(db, allocation_only=allocation_only)

    if not holdings:
        return []

    # Batch classify
    classification_service = ClassificationService()
    holding_keys = [(h.account_id, h.ticker) for h in holdings]
    classifications = classification_service.classify_holdings_batch(db, holding_keys)

    # Aggregate market_value by (account_id, asset_class_name)
    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for holding in holdings:
        if holding.market_value is None or holding.ticker == ZERO_BALANCE_TICKER:
            continue
        asset_class = classifications.get((holding.account_id, holding.ticker))
        class_name = asset_class.name if asset_class else "Unclassified"
        totals[(holding.account_id, class_name)] += holding.market_value

    # Build account name map
    account_ids = {account_id for account_id, _ in totals}
    accounts = db.query(Account).filter(Account.id.in_(account_ids)).all()
    account_name_map = {a.id: a.name for a in accounts}

    # Sort by account name then asset class name
    sorted_keys = sorted(
        totals.keys(),
        key=lambda k: (account_name_map.get(k[0], k[0]), k[1]),
    )

    # Format rows with / continuation
    rows: list[list[str]] = []
    prev_account_id = None
    for account_id, class_name in sorted_keys:
        if account_id == prev_account_id:
            account_label = "/"
        else:
            account_label = account_name_map.get(account_id, account_id)
            prev_account_id = account_id

        value = totals[(account_id, class_name)]
        rows.append([account_label, class_name, f"{value:.2f}"])

    logger.info("Generated %d report rows for %d accounts", len(rows), len(account_ids))

    return rows
