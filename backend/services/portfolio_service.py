"""Unified service for current portfolio data and allocation calculations."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from models import Account, AccountSnapshot, DailyHoldingValue, Holding, SyncSession
from services.classification_service import ClassificationService
from utils.ticker import ZERO_BALANCE_TICKER

logger = logging.getLogger(__name__)

STALE_THRESHOLD_DAYS = 5


@dataclass
class CurrentHolding:
    """A single holding in the current portfolio."""

    account_id: str
    ticker: str
    market_value: Decimal


@dataclass
class CurrentAccountData:
    """Current data for a single account."""

    account_id: str
    total_value: Decimal
    as_of: date
    source: str  # "daily_valuation"
    holdings: list[CurrentHolding] = field(default_factory=list)


@dataclass
class AccountValuationInfo:
    """Valuation health status for a single account."""

    status: Literal["ok", "partial", "missing", "stale"]
    valuation_date: date | None


class PortfolioService:
    """Unified service for current portfolio state and allocation.

    Single source of truth for "what does the portfolio look like right now?"
    Replaces CurrentPortfolioService, parts of ClassificationService, and
    SyncService.get_latest_account_snapshot_ids.
    """

    def get_portfolio_summary(
        self,
        db: Session,
        account_ids: list[str] | None = None,
        allocation_only: bool = False,
    ) -> dict[str, CurrentAccountData]:
        """Get current portfolio data for accounts.

        Always reads from DailyHoldingValue as the single source of truth.
        Sync and manual holding operations create same-day DHV rows, so this
        is always up-to-date.

        Args:
            db: Database session
            account_ids: Optional list of account IDs to include.
                         If None, includes all matching accounts.
            allocation_only: If True, only include accounts with
                            include_in_allocation=True.

        Returns:
            Dict mapping account_id to CurrentAccountData
        """
        active_accounts = self._get_active_accounts(db, account_ids, allocation_only)

        if not active_accounts:
            return {}

        active_ids = [a.id for a in active_accounts]

        # Get latest daily valuation date per account
        daily_dates = self._get_latest_daily_dates(db, active_ids)

        daily_accounts = [
            account_id for account_id in active_ids
            if account_id in daily_dates
        ]

        result: dict[str, CurrentAccountData] = {}

        if daily_accounts:
            result = self._load_daily_data(db, daily_accounts, daily_dates)

        logger.info(
            "Current portfolio: %d accounts (daily_valuation)",
            len(result),
        )

        return result

    def get_current_holdings(
        self,
        db: Session,
        account_ids: list[str] | None = None,
        allocation_only: bool = False,
    ) -> list[CurrentHolding]:
        """Get a flat list of current holdings.

        Args:
            db: Database session
            account_ids: Optional account ID filter
            allocation_only: If True, only allocation accounts

        Returns:
            Flat list of CurrentHolding from all matching accounts
        """
        summary = self.get_portfolio_summary(db, account_ids, allocation_only)
        holdings = []
        for account_data in summary.values():
            holdings.extend(account_data.holdings)
        return holdings

    def get_valuation_status(
        self,
        db: Session,
        account_ids: list[str],
    ) -> dict[str, AccountValuationInfo]:
        """Get valuation health status for each account.

        Compares all Holding rows (including cash equivalents) against
        DailyHoldingValue rows for the latest valuation date. Every
        holding is expected to have a corresponding DHV row.

        Returns a dict mapping account_id to AccountValuationInfo.
        Accounts with no AccountSnapshot are excluded from results.

        Status priority: missing > partial > stale > ok.
        """
        snap_id_map = self._get_latest_account_snapshot_ids(db, account_ids)
        if not snap_id_map:
            return {}

        daily_dates = self._get_latest_daily_dates(db, account_ids, snap_id_map)

        snap_ids = list(snap_id_map.values())
        # Build reverse map: snapshot_id → account_id
        snap_to_account = {v: k for k, v in snap_id_map.items()}

        # Count holdings per account from latest snapshot
        holding_counts = (
            db.query(
                Holding.account_snapshot_id,
                func.count(Holding.id).label("cnt"),
            )
            .filter(Holding.account_snapshot_id.in_(snap_ids))
            .group_by(Holding.account_snapshot_id)
            .all()
        )
        holding_count_by_account: dict[str, int] = {}
        for row in holding_counts:
            account_id = snap_to_account.get(row.account_snapshot_id)
            if account_id is not None:
                holding_count_by_account[account_id] = row.cnt

        # Count DHV rows per (account, valuation_date), excluding _ZERO_BALANCE sentinel
        dhv_conditions = []
        for account_id in snap_id_map:
            val_date = daily_dates.get(account_id)
            if val_date is not None:
                dhv_conditions.append(
                    and_(
                        DailyHoldingValue.account_id == account_id,
                        DailyHoldingValue.valuation_date == val_date,
                    )
                )

        dhv_count_by_account: dict[str, int] = {}
        if dhv_conditions:
            dhv_counts = (
                db.query(
                    DailyHoldingValue.account_id,
                    func.count(DailyHoldingValue.id).label("cnt"),
                )
                .filter(
                    DailyHoldingValue.account_snapshot_id.in_(snap_ids),
                    DailyHoldingValue.ticker != ZERO_BALANCE_TICKER,
                    or_(*dhv_conditions),
                )
                .group_by(DailyHoldingValue.account_id)
                .all()
            )
            for row in dhv_counts:
                dhv_count_by_account[row.account_id] = row.cnt

        result: dict[str, AccountValuationInfo] = {}
        today = datetime.now(timezone.utc).date()

        for account_id in snap_id_map:
            val_date = daily_dates.get(account_id)
            holding_count = holding_count_by_account.get(account_id, 0)
            dhv_count = dhv_count_by_account.get(account_id, 0)

            if val_date is None or (holding_count > 0 and dhv_count == 0):
                # No real DHV rows (val_date may come from _ZERO_BALANCE sentinel)
                result[account_id] = AccountValuationInfo(
                    status="missing", valuation_date=None
                )
            elif dhv_count != holding_count:
                result[account_id] = AccountValuationInfo(
                    status="partial", valuation_date=val_date
                )
            elif (today - val_date).days > STALE_THRESHOLD_DAYS:
                result[account_id] = AccountValuationInfo(
                    status="stale", valuation_date=val_date
                )
            else:
                result[account_id] = AccountValuationInfo(
                    status="ok", valuation_date=val_date
                )

        return result

    def _get_active_accounts(
        self,
        db: Session,
        account_ids: list[str] | None,
        allocation_only: bool,
    ) -> list[Account]:
        """Get active accounts with optional filters."""
        query = db.query(Account).filter(Account.is_active.is_(True))
        if account_ids is not None:
            query = query.filter(Account.id.in_(account_ids))
        if allocation_only:
            query = query.filter(Account.include_in_allocation.is_(True))
        return query.all()

    def _get_latest_account_snapshot_ids(
        self, db: Session, account_ids: list[str]
    ) -> dict[str, str]:
        """Get the latest AccountSnapshot ID per account (by SyncSession timestamp)."""
        from sqlalchemy.orm import aliased
        SyncSessionAlias = aliased(SyncSession)

        # Subquery: max sync session timestamp per account
        latest_ts = (
            db.query(
                AccountSnapshot.account_id,
                func.max(SyncSessionAlias.timestamp).label("max_ts"),
            )
            .join(SyncSessionAlias, AccountSnapshot.sync_session_id == SyncSessionAlias.id)
            .filter(AccountSnapshot.account_id.in_(account_ids))
            .group_by(AccountSnapshot.account_id)
            .subquery()
        )

        # Main query: get snapshot IDs matching latest timestamp
        rows = (
            db.query(AccountSnapshot.account_id, AccountSnapshot.id)
            .join(SyncSessionAlias, AccountSnapshot.sync_session_id == SyncSessionAlias.id)
            .join(
                latest_ts,
                (AccountSnapshot.account_id == latest_ts.c.account_id)
                & (SyncSessionAlias.timestamp == latest_ts.c.max_ts),
            )
            .all()
        )

        return {row.account_id: row.id for row in rows}

    def _get_latest_daily_dates(
        self,
        db: Session,
        account_ids: list[str],
        snap_id_map: dict[str, str] | None = None,
    ) -> dict[str, date]:
        """Get the latest daily valuation date for each account.

        Only considers DHV rows from the latest AccountSnapshot per account,
        so liquidated accounts (newest snapshot with no DHV) are correctly
        excluded.

        Args:
            snap_id_map: Pre-computed latest snapshot IDs per account.
                         If None, will be fetched internally.
        """
        if snap_id_map is None:
            snap_id_map = self._get_latest_account_snapshot_ids(db, account_ids)
        if not snap_id_map:
            return {}

        snap_ids = list(snap_id_map.values())

        rows = (
            db.query(
                DailyHoldingValue.account_id,
                func.max(DailyHoldingValue.valuation_date).label("max_date"),
            )
            .filter(DailyHoldingValue.account_snapshot_id.in_(snap_ids))
            .group_by(DailyHoldingValue.account_id)
            .all()
        )
        return {row.account_id: row.max_date for row in rows}

    def _load_daily_data(
        self,
        db: Session,
        account_ids: list[str],
        daily_dates: dict[str, date],
    ) -> dict[str, CurrentAccountData]:
        """Load current data from daily holding values (batch)."""
        if not account_ids:
            return {}

        # Get latest snapshot IDs so we only load DHV from current snapshots
        snap_id_map = self._get_latest_account_snapshot_ids(db, account_ids)
        if not snap_id_map:
            return {}

        snap_ids = list(snap_id_map.values())

        # Build OR conditions for each (account_id, date) pair
        from sqlalchemy import and_, or_
        conditions = []
        for account_id in account_ids:
            val_date = daily_dates.get(account_id)
            if val_date is not None:
                conditions.append(
                    and_(
                        DailyHoldingValue.account_id == account_id,
                        DailyHoldingValue.valuation_date == val_date,
                    )
                )

        if not conditions:
            return {}

        rows = (
            db.query(DailyHoldingValue)
            .filter(DailyHoldingValue.account_snapshot_id.in_(snap_ids))
            .filter(or_(*conditions))
            .all()
        )

        # Group by account_id
        holdings_by_account: dict[str, list[CurrentHolding]] = {}
        for row in rows:
            holdings_by_account.setdefault(row.account_id, []).append(
                CurrentHolding(
                    account_id=row.account_id,
                    ticker=row.ticker,
                    market_value=row.market_value,
                )
            )

        result: dict[str, CurrentAccountData] = {}
        for account_id in account_ids:
            current_holdings = holdings_by_account.get(account_id, [])
            if not current_holdings:
                continue
            total_value = sum(h.market_value for h in current_holdings)
            result[account_id] = CurrentAccountData(
                account_id=account_id,
                total_value=total_value,
                as_of=daily_dates[account_id],
                source="daily_valuation",
                holdings=current_holdings,
            )

        return result

    def calculate_allocation(
        self,
        db: Session,
        account_ids: list[str] | None = None,
        allocation_only: bool = False,
    ) -> dict:
        """Calculate asset allocation from current holdings.

        Uses batch classification (2 DB queries) instead of per-holding queries.

        Args:
            db: Database session
            account_ids: Optional account ID filter
            allocation_only: If True, only allocation accounts

        Returns:
            Dict with:
            - by_type: {asset_type_id: {name, color, value, percent}}
            - unassigned: {value, percent}
            - total: total portfolio value
        """
        holdings = self.get_current_holdings(db, account_ids, allocation_only)

        if not holdings:
            return {
                "by_type": {},
                "unassigned": {"value": Decimal("0.00"), "percent": Decimal("0.00")},
                "total": Decimal("0.00"),
            }

        # Batch classify all holdings (2 queries)
        classification_service = ClassificationService()
        holding_keys = [(h.account_id, h.ticker) for h in holdings]
        classifications = classification_service.classify_holdings_batch(
            db, holding_keys
        )

        by_type: dict[str, dict] = {}
        unassigned_value = Decimal("0.00")
        total_value = Decimal("0.00")

        for holding in holdings:
            total_value += holding.market_value
            asset_type = classifications.get((holding.account_id, holding.ticker))

            if asset_type:
                if asset_type.id not in by_type:
                    by_type[asset_type.id] = {
                        "name": asset_type.name,
                        "color": asset_type.color,
                        "value": Decimal("0.00"),
                    }
                by_type[asset_type.id]["value"] += holding.market_value
            else:
                unassigned_value += holding.market_value

        # Calculate percentages
        for type_id in by_type:
            by_type[type_id]["percent"] = (
                (by_type[type_id]["value"] / total_value * 100)
                if total_value > 0
                else Decimal("0.00")
            )

        unassigned_percent = (
            (unassigned_value / total_value * 100)
            if total_value > 0
            else Decimal("0.00")
        )

        return {
            "by_type": by_type,
            "unassigned": {"value": unassigned_value, "percent": unassigned_percent},
            "total": total_value,
        }

    def get_holdings_for_asset_type(
        self,
        db: Session,
        asset_type_id: str,
        account_ids: list[str] | None = None,
        allocation_only: bool = False,
    ) -> list[dict]:
        """Get individual holdings classified under a specific asset type.

        Reads from latest DailyHoldingValue per account (consistent with
        get_portfolio_summary). For asset_type_id="unassigned", returns
        holdings where classification is None.

        Args:
            db: Database session
            asset_type_id: Asset type ID, or "unassigned" for unclassified
            account_ids: Optional account ID filter
            allocation_only: If True, only allocation accounts

        Returns:
            List of holding dicts with account_name, security_name, etc.
        """
        # Get active accounts for filtering
        active_accounts = self._get_active_accounts(db, account_ids, allocation_only)
        if not active_accounts:
            return []

        active_ids = [a.id for a in active_accounts]
        account_name_map = {a.id: a.name for a in active_accounts}

        # Get latest daily valuation date per account
        daily_dates = self._get_latest_daily_dates(db, active_ids)
        if not daily_dates:
            return []

        # Load DailyHoldingValue rows for the latest date per account
        from sqlalchemy import and_, or_
        conditions = []
        for account_id in active_ids:
            val_date = daily_dates.get(account_id)
            if val_date is not None:
                conditions.append(
                    and_(
                        DailyHoldingValue.account_id == account_id,
                        DailyHoldingValue.valuation_date == val_date,
                    )
                )

        if not conditions:
            return []

        dhv_rows = (
            db.query(DailyHoldingValue)
            .options(joinedload(DailyHoldingValue.security))
            .filter(or_(*conditions))
            .all()
        )

        if not dhv_rows:
            return []

        # Batch classify
        classification_service = ClassificationService()
        holding_keys = [(dhv.account_id, dhv.ticker) for dhv in dhv_rows]

        classifications = classification_service.classify_holdings_batch(
            db, holding_keys
        )

        result = []
        for dhv in dhv_rows:
            asset_type = classifications.get((dhv.account_id, dhv.ticker))

            match = False
            if asset_type_id == "unassigned":
                match = asset_type is None
            elif asset_type and asset_type.id == asset_type_id:
                match = True

            if match:
                result.append(
                    {
                        "holding_id": dhv.id,
                        "account_id": dhv.account_id,
                        "account_name": account_name_map.get(dhv.account_id, dhv.account_id),
                        "ticker": dhv.ticker,
                        "security_name": dhv.security.name if dhv.security else None,
                        "market_value": dhv.market_value,
                    }
                )

        logger.info(
            "Found %d holdings for asset type %s",
            len(result),
            asset_type_id,
        )
        return result
