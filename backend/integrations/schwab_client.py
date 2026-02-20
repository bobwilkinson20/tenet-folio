"""Charles Schwab API client.

This module implements the ProviderClient protocol for Charles Schwab
integration via the schwab-py library, fetching accounts, positions,
and transactions using the Individual Trader API.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from httpx import ConnectError, ReadTimeout, RemoteProtocolError

from schwab.auth import client_from_token_file
from schwab.client import Client

from config import settings
from integrations.parsing_utils import parse_iso_datetime
from integrations.provider_protocol import (
    ErrorCategory,
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncError,
    ProviderSyncResult,
)

logger = logging.getLogger(__name__)

# Mapping from Schwab transaction types to simplified activity types.
# Schwab types: TRADE, RECEIVE_AND_DELIVER, DIVIDEND_OR_INTEREST,
# ACH_RECEIPT, ACH_DISBURSEMENT, CASH_RECEIPT, CASH_DISBURSEMENT,
# ELECTRONIC_FUND, WIRE_OUT, WIRE_IN, JOURNAL, MEMORANDUM,
# MARGIN_CALL, MONEY_MARKET, SMA_ADJUSTMENT
TRANSACTION_TYPE_MAP: dict[str, str] = {
    "TRADE": "trade",  # further refined by sub-type / transferItems
    "RECEIVE_AND_DELIVER": "transfer",
    "DIVIDEND_OR_INTEREST": "dividend",
    "ACH_RECEIPT": "deposit",
    "ACH_DISBURSEMENT": "withdrawal",
    "CASH_RECEIPT": "deposit",
    "CASH_DISBURSEMENT": "withdrawal",
    "ELECTRONIC_FUND": "transfer",
    "WIRE_IN": "deposit",
    "WIRE_OUT": "withdrawal",
    "JOURNAL": "transfer",
    "MEMORANDUM": "other",
    "MARGIN_CALL": "other",
    "MONEY_MARKET": "other",
    "SMA_ADJUSTMENT": "other",
}

# Trade sub-types that indicate a buy
BUY_SUB_TYPES = frozenset({"BY", "BUY", "BUY TO OPEN", "BUY TO CLOSE"})

# Trade sub-types that indicate a sell
SELL_SUB_TYPES = frozenset({"SL", "SELL", "SELL TO OPEN", "SELL TO CLOSE",
                            "SELL SHORT", "SHORT SALE"})


class SchwabClient:
    """Wrapper around the Charles Schwab Individual Trader API.

    Implements the ProviderClient protocol for multi-provider support.
    Uses schwab-py to authenticate via OAuth token file and fetch
    account, position, and transaction data.
    """

    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        callback_url: str | None = None,
        token_path: str | None = None,
    ):
        """Initialize the client with credentials.

        Args:
            app_key: Schwab application key (defaults to settings).
            app_secret: Schwab application secret (defaults to settings).
            callback_url: OAuth callback URL (defaults to settings).
            token_path: Path to token JSON file (defaults to settings).
        """
        self._app_key = app_key or settings.SCHWAB_APP_KEY
        self._app_secret = app_secret or settings.SCHWAB_APP_SECRET
        self._callback_url = callback_url or settings.SCHWAB_CALLBACK_URL
        self._token_path = token_path or settings.SCHWAB_TOKEN_PATH

        # Lazily created on first use
        self._client: Client | None = None

        # Cache: account_hash -> account_number mapping
        self._account_hash_map: dict[str, str] | None = None

    def _get_client(self) -> Client:
        """Return (and cache) an authenticated schwab-py client."""
        if self._client is None:
            self._client = client_from_token_file(
                token_path=self._token_path,
                api_key=self._app_key,
                app_secret=self._app_secret,
            )
        return self._client

    def _retry_request(self, fn, *, retries=3, base_delay=1.0):
        """Call fn(), retrying on transient httpx connection errors."""
        for attempt in range(retries):
            try:
                return fn()
            except (RemoteProtocolError, ConnectError, ReadTimeout) as exc:
                if attempt == retries - 1:
                    raise
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Schwab API request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, retries, delay, exc,
                )
                time.sleep(delay)

    def _get_account_hash_map(self) -> dict[str, str]:
        """Fetch and cache the account hash -> account number mapping.

        Returns:
            Dict mapping account hash values to account numbers.
        """
        if self._account_hash_map is not None:
            return self._account_hash_map

        client = self._get_client()
        resp = self._retry_request(lambda: client.get_account_numbers())
        resp.raise_for_status()
        data = resp.json()

        self._account_hash_map = {}
        for entry in data:
            hash_val = entry.get("hashValue", "")
            acct_num = entry.get("accountNumber", "")
            if hash_val:
                self._account_hash_map[hash_val] = acct_num

        return self._account_hash_map

    def _get_number_to_hash_map(self) -> dict[str, str]:
        """Return account number -> hash mapping (reverse of hash map).

        The ``get_accounts()`` endpoint does **not** include account hashes.
        This reverse mapping lets us look up the hash for an account using
        the ``accountNumber`` that *is* present in both responses.

        Returns:
            Dict mapping account numbers to hash values.
        """
        hash_map = self._get_account_hash_map()
        return {number: hash_val for hash_val, number in hash_map.items()}

    @property
    def provider_name(self) -> str:
        """Return the provider name for database storage."""
        return "Schwab"

    def is_configured(self) -> bool:
        """Check if Schwab credentials and token file are present.

        Returns:
            True if app key, app secret, and token file all exist.
        """
        if not self._app_key or not self._app_secret:
            return False
        if not self._token_path:
            return False
        return Path(self._token_path).exists()

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def get_accounts(self) -> list[ProviderAccount]:
        """Fetch all accounts from Schwab.

        Uses get_accounts(fields=POSITIONS) to get account details.
        Account hashes are used as the external ID since they are
        stable and required for all other API calls.

        Note: ``get_accounts()`` does **not** return account hashes.
        We join on ``accountNumber`` via ``get_account_numbers()`` to
        resolve the hash for each account.

        Returns:
            List of ProviderAccount objects.
        """
        client = self._get_client()
        number_to_hash = self._get_number_to_hash_map()

        resp = self._retry_request(
            lambda: client.get_accounts(fields=Client.Account.Fields.POSITIONS)
        )
        resp.raise_for_status()
        data = resp.json()

        accounts: list[ProviderAccount] = []
        for acct_data in data:
            account = self._map_account(acct_data, number_to_hash)
            if account is not None:
                accounts.append(account)
        return accounts

    def _map_account(
        self, acct_data: dict, number_to_hash: dict[str, str]
    ) -> ProviderAccount | None:
        """Map a Schwab account response to a ProviderAccount.

        The ``get_accounts()`` response does not include ``hashValue``.
        We resolve the hash by looking up ``securitiesAccount.accountNumber``
        in the *number_to_hash* mapping (built from ``get_account_numbers()``).

        Args:
            acct_data: Raw account dict from the API.
            number_to_hash: Account number -> hash mapping.

        Returns:
            ProviderAccount or None if unmappable.
        """
        sec_acct = acct_data.get("securitiesAccount", {})
        acct_number = sec_acct.get("accountNumber", "")
        account_hash = number_to_hash.get(acct_number, "")
        if not account_hash:
            return None

        acct_type = sec_acct.get("type", "")

        # Build a display name from account type
        if acct_type:
            name = f"Schwab {acct_type.replace('_', ' ').title()} Account"
        else:
            name = "Schwab Account"

        return ProviderAccount(
            id=account_hash,
            name=name,
            institution="Charles Schwab",
            account_number=acct_number or None,
        )

    # ------------------------------------------------------------------
    # Holdings
    # ------------------------------------------------------------------

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Fetch holdings (positions) from Schwab.

        Positions are returned inline with get_accounts(fields=POSITIONS).

        Args:
            account_id: Account hash to filter by. If None, all accounts.

        Returns:
            List of ProviderHolding objects.
        """
        client = self._get_client()
        number_to_hash = self._get_number_to_hash_map()

        resp = self._retry_request(
            lambda: client.get_accounts(fields=Client.Account.Fields.POSITIONS)
        )
        resp.raise_for_status()
        data = resp.json()

        holdings: list[ProviderHolding] = []
        for acct_data in data:
            sec_acct = acct_data.get("securitiesAccount", {})
            acct_number = sec_acct.get("accountNumber", "")
            acct_hash = number_to_hash.get(acct_number, "")
            if account_id and acct_hash != account_id:
                continue
            holdings.extend(
                self._extract_holdings_from_account(acct_data, acct_hash)
            )
        return holdings

    def _extract_holdings_from_account(
        self, acct_data: dict, account_hash: str = ""
    ) -> list[ProviderHolding]:
        """Extract positions and cash from a single account response.

        Args:
            acct_data: Raw account dict from the API.
            account_hash: The resolved account hash for this account.
        """
        sec_acct = acct_data.get("securitiesAccount", {})
        positions = sec_acct.get("positions", []) or []

        holdings: list[ProviderHolding] = []
        for pos in positions:
            holding = self._map_position(pos, account_hash)
            if holding is not None:
                holdings.append(holding)

        # Add cash balance as synthetic holding
        cash_holding = self._extract_cash_balance(sec_acct, account_hash)
        if cash_holding is not None:
            holdings.append(cash_holding)

        return holdings

    def _map_position(
        self, pos: dict, account_hash: str
    ) -> ProviderHolding | None:
        """Map a Schwab position to a ProviderHolding.

        Args:
            pos: Raw position dict from the API.
            account_hash: The account hash this position belongs to.

        Returns:
            ProviderHolding or None if the position can't be mapped.
        """
        instrument = pos.get("instrument", {}) or {}
        symbol = instrument.get("symbol")
        if not symbol:
            return None

        long_qty = self._to_decimal(pos.get("longQuantity")) or Decimal("0")
        short_qty = self._to_decimal(pos.get("shortQuantity")) or Decimal("0")
        quantity = long_qty - short_qty

        if quantity == Decimal("0"):
            return None

        market_value = self._to_decimal(pos.get("marketValue")) or Decimal("0")

        # Derive price from market_value / quantity
        if quantity != Decimal("0"):
            price = market_value / quantity
        else:
            price = Decimal("0")

        # Extract per-unit cost basis
        cost_basis = self._to_decimal(pos.get("averagePrice"))
        if cost_basis is not None and cost_basis <= 0:
            cost_basis = None

        return ProviderHolding(
            account_id=account_hash,
            symbol=symbol,
            quantity=quantity,
            price=price,
            market_value=market_value,
            currency="USD",
            name=instrument.get("description"),
            cost_basis=cost_basis,
            raw_data=pos,
        )

    def _extract_cash_balance(
        self, sec_acct: dict, account_hash: str
    ) -> ProviderHolding | None:
        """Extract cash balance as a synthetic _CASH:USD holding.

        Args:
            sec_acct: The securitiesAccount dict.
            account_hash: The account hash.

        Returns:
            ProviderHolding for cash or None if zero/missing.
        """
        balances = sec_acct.get("currentBalances", {}) or {}
        cash_balance = self._to_decimal(balances.get("cashBalance"))

        if cash_balance is None or cash_balance == Decimal("0"):
            return None

        return ProviderHolding(
            account_id=account_hash,
            symbol="_CASH:USD",
            quantity=cash_balance,
            price=Decimal("1"),
            market_value=cash_balance,
            currency="USD",
            name="USD Cash",
        )

    # ------------------------------------------------------------------
    # Activities (Transactions)
    # ------------------------------------------------------------------

    def get_activities(
        self, account_id: str | None = None
    ) -> list[ProviderActivity]:
        """Fetch transactions from Schwab.

        Args:
            account_id: Account hash. If None, fetches for all accounts.

        Returns:
            List of ProviderActivity objects.
        """
        if account_id:
            return self._get_transactions_for_account(account_id)

        hash_map = self._get_account_hash_map()
        activities: list[ProviderActivity] = []
        for acct_hash in hash_map:
            try:
                activities.extend(
                    self._get_transactions_for_account(acct_hash)
                )
            except Exception:
                logger.warning(
                    "Failed to fetch transactions for account %s",
                    acct_hash,
                    exc_info=True,
                )
        return activities

    def _get_transactions_for_account(
        self, account_hash: str
    ) -> list[ProviderActivity]:
        """Fetch and map transactions for a single account.

        Fetches the last 60 days of transactions (the Schwab API maximum
        start_date range).

        Args:
            account_hash: The account hash to fetch transactions for.

        Returns:
            List of ProviderActivity objects.
        """
        client = self._get_client()
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=60)

        resp = self._retry_request(
            lambda: client.get_transactions(
                account_hash,
                start_date=start_date,
                end_date=end_date,
            )
        )
        resp.raise_for_status()
        data = resp.json()

        activities: list[ProviderActivity] = []
        for txn in data:
            activity = self._map_transaction(txn, account_hash)
            if activity is not None:
                activities.append(activity)
        return activities

    def _map_transaction(
        self, txn: dict, account_hash: str
    ) -> ProviderActivity | None:
        """Map a Schwab transaction to a ProviderActivity.

        Args:
            txn: Raw transaction dict from the API.
            account_hash: The account hash this transaction belongs to.

        Returns:
            ProviderActivity or None if the transaction can't be mapped.
        """
        # External ID — prefer activityId, fall back to transactionId
        external_id = str(
            txn.get("activityId")
            or txn.get("transactionId")
            or ""
        )
        if not external_id:
            return None

        # Activity date — prefer transactionDate, fall back to tradeDate
        activity_date = parse_iso_datetime(
            txn.get("transactionDate") or txn.get("tradeDate")
        )
        if activity_date is None:
            return None

        # Net amount
        net_amount = self._to_decimal(txn.get("netAmount"))

        # Transaction type mapping
        txn_type = str(txn.get("type", "")).upper()
        txn_sub_type = str(txn.get("transactionSubType", "")).upper()
        activity_type = self._resolve_activity_type(
            txn_type, txn_sub_type, net_amount
        )

        # Description
        description = txn.get("description") or ""

        # Settlement date
        settlement_date = parse_iso_datetime(txn.get("settlementDate"))

        # Extract ticker, units, price, fee from transferItems.
        #
        # Schwab TRADE transactions often contain multiple transferItems:
        #   - CURRENCY items (fees, settlement cash) with symbol like
        #     "CURRENCY_USD" and assetType "CURRENCY"
        #   - The actual security item (EQUITY, MUTUAL_FUND, etc.)
        #
        # We find the first non-currency item for trade details and
        # accumulate costs from all items for fees.
        ticker = None
        units = None
        price = None
        fee = Decimal("0")

        transfer_items = txn.get("transferItems", []) or []
        security_item = None
        for item in transfer_items:
            instrument = item.get("instrument", {}) or {}
            asset_type = (instrument.get("assetType") or "").upper()

            if asset_type != "CURRENCY" and security_item is None:
                security_item = item

            # Accumulate costs (fees/commissions) from all items
            item_cost = self._to_decimal(item.get("cost")) or Decimal("0")
            if item_cost != Decimal("0"):
                fee += abs(item_cost)

        if security_item is not None:
            instrument = security_item.get("instrument", {}) or {}
            ticker = instrument.get("symbol")
            units = self._to_decimal(security_item.get("amount"))
            price = self._to_decimal(security_item.get("price"))

            # For transfers (e.g. RECEIVE_AND_DELIVER), the price field
            # is often null/0. Fall back to closingPrice which Schwab
            # provides on the instrument object.
            if not price:
                closing = self._to_decimal(instrument.get("closingPrice"))
                if closing:
                    price = closing

            # For trades, use the instrument description (security name)
            # instead of Schwab's generic description (e.g. "BUY TRADE").
            # This matches IBKR behaviour where description = security name.
            if activity_type in ("buy", "sell", "trade"):
                instrument_desc = instrument.get("description")
                if instrument_desc:
                    description = instrument_desc

        # Also check fees dict for commission
        fees_dict = txn.get("fees", {}) or {}
        commission = self._to_decimal(fees_dict.get("commission"))
        if commission is not None and commission != Decimal("0"):
            fee += abs(commission)

        # Normalize: None if no fees
        if fee == Decimal("0"):
            fee = None

        # Build raw_data — stringify all values for storage
        try:
            raw_data = {
                k: str(v) if v is not None else None
                for k, v in txn.items()
            }
        except Exception:
            raw_data = None

        # If amount is missing/zero but we have price and units,
        # compute it so transfers reflect the value of the securities.
        amount = net_amount
        if not amount and price and units:
            amount = price * abs(units)

        return ProviderActivity(
            account_id=account_hash,
            external_id=external_id,
            activity_date=activity_date,
            type=activity_type,
            amount=amount,
            description=description or None,
            settlement_date=settlement_date,
            ticker=ticker,
            units=units,
            price=price,
            currency="USD",
            fee=fee,
            raw_data=raw_data,
        )

    def _resolve_activity_type(
        self, txn_type: str, sub_type: str, net_amount: Decimal | None = None
    ) -> str:
        """Resolve a Schwab transaction type and sub-type to an activity type.

        For TRADE transactions, uses the sub-type to distinguish buys
        from sells.  When the sub-type is unrecognised, falls back to
        the sign of ``net_amount`` (negative = buy, positive = sell).
        For other types, uses the TRANSACTION_TYPE_MAP.

        Args:
            txn_type: Schwab transaction type (e.g. "TRADE").
            sub_type: Schwab transaction sub-type (e.g. "BUY").
            net_amount: Net cash amount of the transaction (optional).

        Returns:
            Simplified activity type string.
        """
        if txn_type == "TRADE":
            if sub_type in BUY_SUB_TYPES:
                return "buy"
            if sub_type in SELL_SUB_TYPES:
                return "sell"
            # Fallback: infer from net amount sign
            if net_amount is not None and net_amount != Decimal("0"):
                return "buy" if net_amount < 0 else "sell"
            return "trade"

        return TRANSACTION_TYPE_MAP.get(txn_type, "other")

    # ------------------------------------------------------------------
    # sync_all
    # ------------------------------------------------------------------

    def sync_all(self) -> ProviderSyncResult:
        """Fetch all data from Schwab.

        Returns:
            ProviderSyncResult with holdings, accounts, activities,
            errors, and per-account balance dates.
        """
        errors: list[ProviderSyncError] = []

        # Accounts (with positions inline)
        try:
            client = self._get_client()
            number_to_hash = self._get_number_to_hash_map()
            resp = self._retry_request(
                lambda: client.get_accounts(
                    fields=Client.Account.Fields.POSITIONS,
                )
            )
            resp.raise_for_status()
            accounts_data = resp.json()
        except Exception as e:
            return ProviderSyncResult(
                holdings=[],
                accounts=[],
                errors=[ProviderSyncError(
                    message=f"Failed to fetch Schwab accounts: {e}",
                    category=ErrorCategory.CONNECTION,
                    retriable=True,
                )],
                balance_dates={},
                activities=[],
            )

        # Map accounts
        accounts: list[ProviderAccount] = []
        for acct_data in accounts_data:
            account = self._map_account(acct_data, number_to_hash)
            if account is not None:
                accounts.append(account)

        # Extract holdings from the same response (no extra API call)
        all_holdings: list[ProviderHolding] = []
        balance_dates: dict[str, datetime | None] = {}
        now = datetime.now(timezone.utc)

        for acct_data in accounts_data:
            sec_acct = acct_data.get("securitiesAccount", {})
            acct_number = sec_acct.get("accountNumber", "")
            acct_hash = number_to_hash.get(acct_number, "")
            try:
                holdings = self._extract_holdings_from_account(
                    acct_data, acct_hash
                )
                all_holdings.extend(holdings)
                if acct_hash:
                    balance_dates[acct_hash] = now
            except Exception as e:
                errors.append(ProviderSyncError(
                    message=f"Failed to extract holdings for account {acct_hash}: {e}",
                    category=ErrorCategory.DATA,
                    account_id=acct_hash,
                ))

        # Activities — per-account, best-effort
        activities: list[ProviderActivity] = []
        for account in accounts:
            try:
                acct_activities = self._get_transactions_for_account(
                    account.id
                )
                activities.extend(acct_activities)
            except Exception:
                logger.warning(
                    "Failed to fetch Schwab transactions for %s",
                    account.name,
                    exc_info=True,
                )

        logger.info(
            "Schwab: %d accounts, %d holdings, %d activities fetched",
            len(accounts), len(all_holdings), len(activities),
        )

        return ProviderSyncResult(
            holdings=all_holdings,
            accounts=accounts,
            errors=errors,
            balance_dates=balance_dates,
            activities=activities,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_decimal(value) -> Decimal | None:
        """Convert a value to Decimal, returning None on failure."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
