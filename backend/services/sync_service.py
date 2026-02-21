"""Sync service - handles fetching holdings and creating sync sessions."""

import logging
import threading
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from integrations.exceptions import ProviderAuthError, ProviderError
from integrations.provider_protocol import (
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncError,
    ProviderSyncResult,
)
from integrations.provider_registry import ProviderRegistry, get_provider_registry
from models import Account, AccountSnapshot, Holding, SyncSession
from models.sync_log import SyncLogEntry
from services.activity_service import ActivityService
from services.lot_reconciliation_service import LotReconciliationService
from services.portfolio_valuation_service import PortfolioValuationService
from services.provider_service import ProviderService
from services.security_service import SecurityService

logger = logging.getLogger(__name__)


class SyncService:
    """Service for syncing portfolio data from configured providers."""

    # Class-level lock shared across all instances to prevent concurrent syncs.
    # This works for single-user, single-process applications. For multi-worker
    # deployments, a distributed lock (Redis, file lock) would be required.
    _sync_lock = threading.Lock()

    def __init__(self, provider_registry: Optional[ProviderRegistry] = None):
        """Initialize with optional provider registry for dependency injection.

        Args:
            provider_registry: Registry of configured providers. If None,
                              a default registry will be created on first use.
        """
        self._registry = provider_registry

    @classmethod
    def is_sync_in_progress(cls) -> bool:
        """Check if a sync operation is currently in progress.

        Returns:
            True if sync is in progress, False otherwise
        """
        acquired = cls._sync_lock.acquire(blocking=False)
        if acquired:
            cls._sync_lock.release()
            return False
        return True

    @property
    def registry(self) -> ProviderRegistry:
        """Get the provider registry, creating default if not provided."""
        if self._registry is None:
            self._registry = get_provider_registry()
        return self._registry

    def _upsert_accounts(
        self,
        db: Session,
        provider_name: str,
        remote_accounts: list[ProviderAccount],
    ) -> list[Account]:
        """Upsert accounts from provider data.

        Creates new accounts or updates existing ones. Preserves user-edited
        names.

        Args:
            db: Database session
            provider_name: Name of the provider (e.g., 'SnapTrade', 'SimpleFIN')
            remote_accounts: List of accounts from the provider

        Returns:
            List of upserted Account records (not yet committed)
        """
        upserted = []
        new_count = 0
        existing_count = 0
        for remote in remote_accounts:
            existing = (
                db.query(Account)
                .filter_by(
                    provider_name=provider_name,
                    external_id=remote.id,
                )
                .first()
            )

            if existing:
                # Update existing account, but preserve user-edited name
                if not existing.name_user_edited:
                    existing.name = remote.name
                existing.institution_name = remote.institution
                upserted.append(existing)
                existing_count += 1
            else:
                # Create new account
                account = Account(
                    provider_name=provider_name,
                    external_id=remote.id,
                    name=remote.name,
                    institution_name=remote.institution,
                    is_active=True,
                )
                db.add(account)
                upserted.append(account)
                new_count += 1

        db.flush()  # Ensure new accounts get IDs
        logger.info(
            "%s: accounts upserted (%d new, %d existing)",
            provider_name, new_count, existing_count,
        )
        return upserted

    def sync_account(
        self,
        db: Session,
        account: Account,
        sync_session: SyncSession,
        holdings_by_account: dict[str, list[ProviderHolding]],
        balance_dates: dict[str, datetime | None] | None = None,
    ) -> str:
        """Sync a single account's holdings.

        Args:
            db: Database session
            account: The account to sync
            sync_session: The sync session to add holdings to
            holdings_by_account: Dict mapping external account ID to ProviderHolding list
            balance_dates: Optional dict mapping external account ID to balance date

        Returns:
            "success" if sync succeeded, "stale" if data unchanged, "failed" if error
        """
        # Mark account as syncing (preserve last_sync_error for error parsing)
        account.last_sync_status = "syncing"
        db.flush()

        # Cache for error handler — accessible even if session is tainted
        account_name = account.name
        provider_name = account.provider_name

        try:
            new_balance_date = (
                balance_dates.get(account.external_id) if balance_dates else None
            )

            # Staleness gate: skip if balance_date hasn't advanced
            # Normalize to naive UTC for comparison (SQLite strips tzinfo)
            existing_bd = account.balance_date
            if existing_bd is not None and existing_bd.tzinfo is not None:
                existing_bd = existing_bd.replace(tzinfo=None)
            compare_new_bd = new_balance_date
            if compare_new_bd is not None and compare_new_bd.tzinfo is not None:
                compare_new_bd = compare_new_bd.replace(tzinfo=None)

            if (
                existing_bd is not None
                and compare_new_bd is not None
                and compare_new_bd <= existing_bd
            ):
                logger.info(
                    "Skipping stale account %s (%s): balance_date %s <= %s",
                    account.name, account.provider_name,
                    new_balance_date, account.balance_date,
                )
                account.last_sync_time = datetime.now(timezone.utc)
                account.last_sync_status = "stale"
                return "stale"

            # Get holdings for this account
            account_holdings = holdings_by_account.get(account.external_id, [])

            # Consolidate duplicate holdings by symbol (e.g., Coinbase may
            # return multiple _CASH:USD positions from its portfolio breakdown)
            account_holdings = self._consolidate_holdings(
                account_holdings, account_name, provider_name,
            )

            logger.info(
                "Syncing account %s (%s): %d holdings",
                account_name, provider_name, len(account_holdings),
            )

            # Calculate total value before creating holdings
            total_value = (
                sum(h.market_value for h in account_holdings)
                if account_holdings
                else Decimal("0")
            )

            # Use a savepoint so a failure in this account doesn't roll back
            # previously-synced accounts in the same transaction
            with db.begin_nested():
                # Create AccountSnapshot first (so holdings can reference it)
                account_snapshot = AccountSnapshot(
                    account_id=account.id,
                    sync_session_id=sync_session.id,
                    status="success",
                    total_value=total_value,
                    balance_date=new_balance_date,
                )
                db.add(account_snapshot)
                db.flush()  # Get the account_snapshot ID

                # Create holding records and ensure security records exist
                created_holdings = []
                for remote in account_holdings:
                    # Ensure security record exists and get its ID
                    security = SecurityService.ensure_exists(db, remote.symbol, remote.name)

                    # Create holding record
                    holding = Holding(
                        account_snapshot_id=account_snapshot.id,
                        security_id=security.id,
                        ticker=remote.symbol,
                        quantity=remote.quantity,
                        snapshot_price=remote.price,
                        snapshot_value=remote.market_value,
                    )
                    db.add(holding)
                    created_holdings.append(holding)

                # Create DailyHoldingValue rows for today
                if created_holdings:
                    db.flush()
                    PortfolioValuationService.create_daily_values_for_holdings(
                        db, created_holdings, date.today(), account_id=account.id
                    )
                    PortfolioValuationService.delete_zero_balance_sentinel(
                        db, account.id, date.today()
                    )
                else:
                    PortfolioValuationService.write_zero_balance_sentinel(
                        db, account.id, account_snapshot.id, date.today()
                    )

                # Update account sync status
                account.last_sync_time = datetime.now(timezone.utc)
                account.last_sync_status = "success"
                account.last_sync_error = None

                # Store balance date from provider if available
                if balance_dates and account.external_id in balance_dates:
                    account.balance_date = balance_dates[account.external_id]

            return "success"

        except ProviderError as e:
            logger.warning(
                "Sync failed for account %s (%s): %s",
                account_name, provider_name, e,
            )
            account.last_sync_status = "failed"
            account.last_sync_error = str(e)

            # Record failed sync in sync session
            account_snapshot = AccountSnapshot(
                account_id=account.id,
                sync_session_id=sync_session.id,
                status="failed",
                total_value=Decimal("0"),
            )
            db.add(account_snapshot)

            return "failed"

        except Exception as e:
            logger.error(
                "Unexpected error syncing account %s (%s): %s",
                account_name, provider_name, e, exc_info=True,
            )
            account.last_sync_status = "failed"
            account.last_sync_error = str(e)

            # Record failed sync in sync session
            account_snapshot = AccountSnapshot(
                account_id=account.id,
                sync_session_id=sync_session.id,
                status="failed",
                total_value=Decimal("0"),
            )
            db.add(account_snapshot)

            return "failed"

    @staticmethod
    def _consolidate_holdings(
        holdings: list[ProviderHolding],
        account_name: str,
        provider_name: str,
    ) -> list[ProviderHolding]:
        """Merge holdings that share the same symbol.

        Some providers (e.g., Coinbase) return multiple positions for the same
        symbol.  The holdings table has a unique constraint on
        (account_snapshot_id, security_id), so duplicates must be consolidated
        before insertion.

        Args:
            holdings: Raw list of ProviderHolding from the provider
            account_name: Account name for logging
            provider_name: Provider name for logging

        Returns:
            De-duplicated list with quantities and values summed per symbol
        """
        if not holdings:
            return holdings

        seen: dict[str, ProviderHolding] = {}
        for h in holdings:
            if h.symbol in seen:
                existing = seen[h.symbol]
                merged_qty = existing.quantity + h.quantity
                merged_value = existing.market_value + h.market_value
                merged_price = (
                    merged_value / merged_qty if merged_qty else Decimal("0")
                )
                seen[h.symbol] = ProviderHolding(
                    symbol=existing.symbol,
                    name=existing.name,
                    quantity=merged_qty,
                    price=merged_price,
                    market_value=merged_value,
                    currency=existing.currency,
                    account_id=existing.account_id,
                )
            else:
                seen[h.symbol] = h

        consolidated = list(seen.values())
        if len(consolidated) < len(holdings):
            dupes = len(holdings) - len(consolidated)
            logger.warning(
                "Merged %d duplicate holdings for account %s (%s): %s",
                dupes,
                account_name,
                provider_name,
                ", ".join(
                    s for s in seen
                    if sum(1 for hh in holdings if hh.symbol == s) > 1
                ),
            )

        return consolidated

    def trigger_sync(self, db: Session) -> SyncSession:
        """Fetch holdings from all configured providers and create a sync session.

        Performs a unified sync: upserts accounts from providers, then fetches
        and stores holdings for all active accounts. Always returns a SyncSession
        (never raises). Success/failure is communicated via is_complete and
        sync_log_entries.

        Args:
            db: Database session

        Returns:
            The created SyncSession with sync_log_entries populated

        Raises:
            ValueError: If sync is already in progress
        """
        # Try to acquire lock without blocking
        acquired = self._sync_lock.acquire(blocking=False)
        if not acquired:
            logger.warning("Sync blocked: another sync is already in progress")
            raise ValueError("Sync already in progress")

        logger.info("Sync lock acquired")
        try:
            # Create new sync session
            sync_session = SyncSession(is_complete=False)
            db.add(sync_session)
            db.flush()  # Get the sync session ID

            logger.info("Sync started")

            try:
                # Get all configured providers, filtering out disabled ones
                provider_names = self.registry.list_providers()
                provider_names = [
                    n for n in provider_names
                    if ProviderService.is_provider_enabled(db, n)
                ]

                if not provider_names:
                    logger.warning("No providers configured")
                    sync_session.is_complete = False
                    sync_session.error_message = "No providers configured"
                    db.commit()
                    return sync_session

                # Sync from each provider
                any_synced = False
                errors = []

                for provider_name in provider_names:
                    try:
                        # Wrap each provider in a savepoint so a partial flush
                        # from a failed provider is rolled back cleanly before
                        # the next provider runs.
                        with db.begin_nested():
                            synced = self._sync_provider_accounts(
                                db, provider_name, sync_session
                            )
                            if synced:
                                any_synced = True
                    except ProviderAuthError as e:
                        error_msg = str(e)
                        errors.append(f"{provider_name}: {error_msg}")
                        logger.warning(
                            "Auth error for provider %s: %s",
                            provider_name, error_msg,
                        )
                        self._mark_provider_accounts_failed(
                            db, provider_name, error_msg
                        )
                        self._create_failed_log_entry(
                            db, sync_session, provider_name, error_msg
                        )
                    except ProviderError as e:
                        error_msg = str(e)
                        errors.append(f"{provider_name}: {error_msg}")
                        logger.warning(
                            "Provider error for %s: %s",
                            provider_name, error_msg,
                        )
                        self._mark_provider_accounts_failed(
                            db, provider_name, error_msg
                        )
                        self._create_failed_log_entry(
                            db, sync_session, provider_name, error_msg
                        )
                    except Exception as e:
                        # Safety net for unexpected errors
                        error_msg = str(e)
                        errors.append(f"{provider_name}: {error_msg}")
                        logger.error(
                            "Unexpected error for provider %s: %s",
                            provider_name, e, exc_info=True,
                        )
                        self._mark_provider_accounts_failed(
                            db, provider_name, error_msg
                        )
                        self._create_failed_log_entry(
                            db, sync_session, provider_name, error_msg
                        )

                # Mark sync session as complete if any account was synced
                sync_session.is_complete = any_synced
                if not any_synced:
                    if errors:
                        sync_session.error_message = "; ".join(errors)
                    else:
                        sync_session.error_message = "No accounts synced"
                db.commit()

                if any_synced:
                    logger.info("Sync completed: session %s", sync_session.id[:8])
                else:
                    logger.warning("Sync finished with no accounts synced")

            except Exception as e:
                # Safety catch for truly unexpected errors
                logger.error("Sync failed: %s", e, exc_info=True)
                sync_session.is_complete = False
                sync_session.error_message = str(e)
                db.commit()

            return sync_session
        finally:
            logger.info("Sync lock released")
            self._sync_lock.release()

    @staticmethod
    def _mark_provider_accounts_failed(
        db: Session,
        provider_name: str,
        error_msg: str,
    ) -> None:
        """Mark all active accounts from a provider as failed.

        Args:
            db: Database session
            provider_name: Name of the failed provider
            error_msg: Error message to store on each account
        """
        provider_accounts = (
            db.query(Account)
            .filter(
                Account.provider_name == provider_name,
                Account.is_active.is_(True),
            )
            .all()
        )
        for account in provider_accounts:
            account.last_sync_status = "failed"
            account.last_sync_error = f"Provider error: {error_msg}"

    @staticmethod
    def _create_failed_log_entry(
        db: Session,
        sync_session: SyncSession,
        provider_name: str,
        error_msg: str,
    ) -> None:
        """Create a failed SyncLogEntry for a provider.

        Args:
            db: Database session
            sync_session: Current sync session
            provider_name: Name of the failed provider
            error_msg: Error message to record
        """
        log_entry = SyncLogEntry(
            sync_session_id=sync_session.id,
            provider_name=provider_name,
            status="failed",
            error_messages=[error_msg],
            accounts_synced=0,
        )
        db.add(log_entry)

    @staticmethod
    def _apply_provider_errors_to_accounts(
        db: Session,
        accounts: list[Account],
        errors: list[ProviderSyncError],
    ) -> None:
        """Apply structured provider errors to matching accounts.

        Matches errors by institution_name or account_id (direct match,
        no regex needed). Falls back to message-only for unmatched errors.

        Args:
            db: Database session
            accounts: Active accounts for this provider
            errors: Structured error objects from the provider
        """
        if not errors or not accounts:
            return

        for error in errors:
            # Match by account_id first (most specific)
            if error.account_id:
                for account in accounts:
                    if account.external_id == error.account_id:
                        account.last_sync_status = "error"
                        account.last_sync_error = str(error)
                        logger.info(
                            "Marked account %s as error (by account_id): %s",
                            account.name, error,
                        )
                continue

            # Match by institution_name (case-insensitive)
            if error.institution_name:
                institution = error.institution_name.strip().lower()
                for account in accounts:
                    if (
                        account.institution_name
                        and account.institution_name.strip().lower() == institution
                    ):
                        account.last_sync_status = "error"
                        account.last_sync_error = str(error)
                        logger.info(
                            "Marked account %s as error (by institution): %s",
                            account.name, error,
                        )

        db.flush()

    def _sync_provider_accounts(
        self,
        db: Session,
        provider_name: str,
        sync_session: SyncSession,
    ) -> bool:
        """Sync accounts and holdings from a specific provider.

        Fetches data from the provider, upserts accounts, then creates
        holdings for each active account.

        Args:
            db: Database session
            provider_name: Name of the provider
            sync_session: The sync session to add holdings to

        Returns:
            True if any account was synced or provider was contacted successfully

        Raises:
            ValueError: If provider is not configured
            Exception: If provider API call fails
        """
        logger.info("Syncing provider: %s", provider_name)
        provider = self.registry.get_provider(provider_name)

        # Use sync_all() if available, otherwise fall back to get_holdings()
        sync_result: ProviderSyncResult | None = None
        if hasattr(provider, "sync_all"):
            if provider_name == "Plaid":
                from models.plaid_item import PlaidItem
                plaid_items = db.query(PlaidItem).all()
                access_tokens = [
                    (item.access_token, item.institution_name or "Unknown")
                    for item in plaid_items
                ]
                sync_result = provider.sync_all(access_tokens=access_tokens)
            else:
                sync_result = provider.sync_all()
            remote_holdings = sync_result.holdings
        else:
            remote_holdings = provider.get_holdings()

        # Upsert accounts from provider data
        if sync_result and sync_result.accounts:
            self._upsert_accounts(db, provider_name, sync_result.accounts)

        # Get all active accounts for this provider (including newly created ones)
        accounts = (
            db.query(Account)
            .filter(
                Account.provider_name == provider_name,
                Account.is_active.is_(True),
            )
            .all()
        )

        # Group holdings by account external_id
        holdings_by_account: dict[str, list[ProviderHolding]] = {}
        for holding in remote_holdings:
            if holding.account_id not in holdings_by_account:
                holdings_by_account[holding.account_id] = []
            holdings_by_account[holding.account_id].append(holding)

        # Extract balance dates from sync result
        balance_dates = sync_result.balance_dates if sync_result else {}

        # Build set of account external_ids the provider actually returned.
        # Accounts absent from the response are skipped entirely — syncing
        # them would create empty $0 snapshots and wipe out valid data.
        responded_ids: set[str] = set()
        if sync_result and sync_result.accounts:
            responded_ids.update(a.id for a in sync_result.accounts)
        responded_ids.update(holdings_by_account.keys())
        if balance_dates:
            responded_ids.update(balance_dates.keys())

        # Apply provider errors to matching accounts before per-account sync
        provider_errors = sync_result.errors if sync_result else []
        if provider_errors:
            self._apply_provider_errors_to_accounts(db, accounts, provider_errors)

        # Capture previous snapshots for lot reconciliation (before sync loop)
        previous_snapshots: dict[str, AccountSnapshot] = {}
        for account in accounts:
            prev_snap = (
                db.query(AccountSnapshot)
                .join(SyncSession, AccountSnapshot.sync_session_id == SyncSession.id)
                .filter(
                    AccountSnapshot.account_id == account.id,
                    AccountSnapshot.status == "success",
                )
                .order_by(SyncSession.timestamp.desc())
                .first()
            )
            if prev_snap:
                previous_snapshots[account.id] = prev_snap

        # Sync each account that the provider returned data for
        any_synced = False
        synced_count = 0
        stale_count = 0
        skipped_count = 0
        account_sync_results: dict[str, str] = {}
        error_count = 0
        for account in accounts:
            if responded_ids and account.external_id not in responded_ids:
                logger.warning(
                    "Account %s (%s): not in provider response — may need attention",
                    account.name, account.provider_name,
                )
                account.last_sync_status = "skipped"
                account.last_sync_error = (
                    "Account not returned by provider — connection may need attention"
                )
                account.last_sync_time = datetime.now(timezone.utc)
                skipped_count += 1
                continue

            # Skip accounts with no data when provider reported errors —
            # syncing them would create empty $0 snapshots and wipe out
            # previous valid data.
            account_ext_holdings = holdings_by_account.get(account.external_id, [])
            account_balance_date = balance_dates.get(account.external_id) if balance_dates else None
            if provider_errors and not account_ext_holdings and not account_balance_date:
                error_strs = [str(e) for e in provider_errors]
                logger.warning(
                    "Skipping account %s (%s): provider reported errors and no data returned — %s",
                    account.name, account.provider_name, "; ".join(error_strs),
                )
                account.last_sync_status = "error"
                account.last_sync_error = "; ".join(error_strs)
                account.last_sync_time = datetime.now(timezone.utc)
                error_count += 1
                continue

            result = self.sync_account(
                db, account, sync_session, holdings_by_account,
                balance_dates=balance_dates,
            )
            account_sync_results[account.id] = result
            if result == "success":
                any_synced = True
                synced_count += 1
            elif result == "stale":
                stale_count += 1

        logger.info(
            "%s: %d/%d accounts synced, %d stale, %d skipped, %d error",
            provider_name, synced_count, len(accounts), stale_count,
            skipped_count, error_count,
        )

        # Sync activities (best-effort — failures don't block holdings sync)
        if sync_result and sync_result.activities:
            activities_by_account: dict[str, list[ProviderActivity]] = {}
            for activity in sync_result.activities:
                if activity.account_id not in activities_by_account:
                    activities_by_account[activity.account_id] = []
                activities_by_account[activity.account_id].append(activity)

            for account in accounts:
                account_activities = activities_by_account.get(
                    account.external_id, []
                )
                if account_activities:
                    try:
                        with db.begin_nested():
                            ActivityService.sync_activities(
                                db, provider_name, account, account_activities
                            )
                    except Exception as e:
                        logger.warning(
                            "Activity sync failed for account %s: %s",
                            account.id,
                            e,
                        )

        # Lot reconciliation (best-effort — failures don't block sync)
        for account in accounts:
            if account_sync_results.get(account.id) != "success":
                continue
            try:
                # Find the current snapshot just created for this account
                current_snapshot = (
                    db.query(AccountSnapshot)
                    .filter_by(
                        account_id=account.id,
                        sync_session_id=sync_session.id,
                        status="success",
                    )
                    .first()
                )
                if not current_snapshot:
                    continue

                prev_snapshot = previous_snapshots.get(account.id)
                account_provider_holdings = holdings_by_account.get(
                    account.external_id, []
                )

                with db.begin_nested():
                    LotReconciliationService.reconcile_account(
                        db,
                        account,
                        prev_snapshot,
                        current_snapshot,
                        sync_session,
                        provider_holdings=account_provider_holdings,
                    )
            except Exception as e:
                logger.warning(
                    "Lot reconciliation failed for account %s: %s",
                    account.id,
                    e,
                )

        # Determine log entry status
        if provider_errors and (any_synced or stale_count > 0):
            status = "partial"
        elif provider_errors and not any_synced and stale_count == 0:
            status = "failed"
        else:
            status = "success"

        # Create sync log entry (convert structured errors to strings for storage)
        error_strings = [str(e) for e in provider_errors] if provider_errors else None
        log_entry = SyncLogEntry(
            sync_session_id=sync_session.id,
            provider_name=provider_name,
            status=status,
            error_messages=error_strings,
            accounts_synced=synced_count,
            accounts_stale=stale_count,
            accounts_error=error_count,
        )
        db.add(log_entry)

        return any_synced or stale_count > 0
