"""SnapTrade API client wrapper.

This module implements the ProviderClient protocol for SnapTrade integration.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from snaptrade_client import SnapTrade

from config import settings
from integrations.exceptions import ProviderAuthError
from integrations.parsing_utils import parse_iso_datetime
from integrations.provider_protocol import (
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncResult,
)

logger = logging.getLogger(__name__)


@dataclass
class SnapTradeAccount:
    """Represents an account from SnapTrade.

    Note: This is kept for backward compatibility. New code should use
    ProviderAccount from provider_protocol.py.
    """

    id: str
    name: str
    brokerage_name: str
    account_number: str | None = None


@dataclass
class SnapTradeHolding:
    """Represents a holding from SnapTrade.

    Note: This is kept for backward compatibility. New code should use
    ProviderHolding from provider_protocol.py.
    """

    account_id: str
    symbol: str
    quantity: float
    price: float
    market_value: float
    currency: str = "USD"
    average_purchase_price: float | None = None
    raw_data: dict | None = None


class SnapTradeClientProtocol(Protocol):
    """Protocol for SnapTrade client to enable mocking.

    Note: This is kept for backward compatibility. New code should use
    ProviderClient from provider_protocol.py.
    """

    def get_accounts(self) -> list[SnapTradeAccount]: ...
    def get_all_holdings(self) -> list[SnapTradeHolding]: ...


class SnapTradeClient:
    """Wrapper around the SnapTrade SDK.

    Implements the ProviderClient protocol for multi-provider support.
    """

    def __init__(
        self,
        client_id: str | None = None,
        consumer_key: str | None = None,
        user_id: str | None = None,
        user_secret: str | None = None,
    ):
        """Initialize the client with credentials.

        Args:
            client_id: SnapTrade client ID (defaults to settings)
            consumer_key: SnapTrade consumer key (defaults to settings)
            user_id: SnapTrade user ID (defaults to settings)
            user_secret: SnapTrade user secret (defaults to settings)
        """
        self._client_id = client_id or settings.SNAPTRADE_CLIENT_ID
        self._consumer_key = consumer_key or settings.SNAPTRADE_CONSUMER_KEY
        self.user_id = user_id or settings.SNAPTRADE_USER_ID
        self.user_secret = user_secret or settings.SNAPTRADE_USER_SECRET

        self.client = SnapTrade(
            consumer_key=self._consumer_key,
            client_id=self._client_id,
        )

    @property
    def provider_name(self) -> str:
        """Return the provider name for database storage."""
        return "SnapTrade"

    def is_configured(self) -> bool:
        """Check if SnapTrade credentials are configured.

        Returns:
            True if all required credentials are present, False otherwise.
        """
        return bool(
            self._client_id
            and self._consumer_key
            and self.user_id
            and self.user_secret
        )

    def _check_credentials(self) -> None:
        """Raise an error if credentials are not configured."""
        if not self.user_id or not self.user_secret:
            raise ProviderAuthError(
                "SnapTrade credentials not configured. "
                "Run 'python scripts/setup_snaptrade.py register' first.",
                provider_name="SnapTrade",
            )
        if not self._client_id or not self._consumer_key:
            raise ProviderAuthError(
                "SnapTrade API credentials not configured. "
                "Set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY in .env",
                provider_name="SnapTrade",
            )

    def get_accounts(self) -> list[SnapTradeAccount]:
        """Fetch list of linked accounts from SnapTrade."""
        self._check_credentials()

        response = self.client.account_information.list_user_accounts(
            user_id=self.user_id,
            user_secret=self.user_secret,
        )

        # Response might be a list directly or have a body attribute
        accounts = response if isinstance(response, list) else response.body

        result = []
        for account in accounts:
            # Handle both dict and object response formats
            if isinstance(account, dict):
                acc_id = str(account.get("id", ""))
                name = account.get("name") or "Unknown Account"
                # institution_name is directly on the account object
                brokerage_name = account.get("institution_name") or self._extract_brokerage_name(
                    account.get("brokerage_authorization")
                )
                account_number = account.get("number")
            else:
                acc_id = str(getattr(account, "id", ""))
                name = getattr(account, "name", None) or "Unknown Account"
                # institution_name is directly on the account object
                brokerage_name = getattr(account, "institution_name", None) or self._extract_brokerage_name(
                    getattr(account, "brokerage_authorization", None)
                )
                account_number = getattr(account, "number", None)

            result.append(
                SnapTradeAccount(
                    id=acc_id,
                    name=name,
                    brokerage_name=brokerage_name,
                    account_number=account_number,
                )
            )

        return result

    def _extract_symbol(self, symbol_data) -> str:
        """Extract symbol string from various response formats."""
        if symbol_data is None:
            return "UNKNOWN"
        if isinstance(symbol_data, str):
            return symbol_data
        # Try dict-style access first (works for dicts and dict-like objects)
        if hasattr(symbol_data, "get"):
            result = symbol_data.get("symbol", "UNKNOWN")
            # Handle nested case where symbol might also be a dict/object
            if hasattr(result, "get") or hasattr(result, "symbol"):
                return self._extract_symbol(result)
            return result if isinstance(result, str) else "UNKNOWN"
        # Try attribute access
        if hasattr(symbol_data, "symbol"):
            result = symbol_data.symbol
            if hasattr(result, "get") or hasattr(result, "symbol"):
                return self._extract_symbol(result)
            return result if isinstance(result, str) else "UNKNOWN"
        return "UNKNOWN"

    def _extract_currency(self, symbol_data) -> str:
        """Extract currency code from symbol data."""
        if symbol_data is None:
            return "USD"
        if isinstance(symbol_data, dict):
            currency = symbol_data.get("currency", {})
            if isinstance(currency, dict):
                return currency.get("code", "USD")
            elif isinstance(currency, str):
                return currency
            return "USD"
        # Object with attributes
        currency = getattr(symbol_data, "currency", None)
        if currency is None:
            return "USD"
        if isinstance(currency, dict):
            return currency.get("code", "USD")
        return getattr(currency, "code", "USD")

    def _extract_brokerage_name(self, brokerage_auth) -> str:
        """Extract brokerage name from various response formats."""
        if brokerage_auth is None:
            return "Unknown"
        if isinstance(brokerage_auth, str):
            # It's just an ID string, not a nested object
            return "Unknown"
        if isinstance(brokerage_auth, dict):
            brokerage = brokerage_auth.get("brokerage")
            if isinstance(brokerage, dict):
                return brokerage.get("name", "Unknown")
            elif isinstance(brokerage, str):
                return brokerage
            elif brokerage and hasattr(brokerage, "name"):
                return getattr(brokerage, "name", "Unknown")
            return "Unknown"
        # Object with attributes
        if hasattr(brokerage_auth, "brokerage"):
            brokerage = brokerage_auth.brokerage
            if isinstance(brokerage, str):
                return brokerage
            elif brokerage and hasattr(brokerage, "name"):
                return getattr(brokerage, "name", "Unknown")
        return "Unknown"

    def get_all_holdings(self) -> list[SnapTradeHolding]:
        """Fetch all holdings across all accounts."""
        self._check_credentials()

        # First get all accounts
        accounts = self.get_accounts()

        holdings = []
        for account in accounts:
            account_holdings = self._get_holdings_for_account(account.id)
            holdings.extend(account_holdings)

        return holdings

    def _get_holdings_for_account(self, account_id: str) -> list[SnapTradeHolding]:
        """Fetch holdings for a specific account."""
        response = self.client.account_information.get_user_holdings(
            account_id=account_id,
            user_id=self.user_id,
            user_secret=self.user_secret,
        )

        # Response might be a dict/object with holdings or have a body attribute
        data = response if isinstance(response, (dict, list)) else response.body

        # Handle different response structures
        if isinstance(data, list):
            # Direct list of positions
            positions = data
        elif isinstance(data, dict):
            # Object with positions/holdings key
            positions = data.get("positions") or data.get("holdings") or []
        else:
            # Object with attributes
            positions = getattr(data, "positions", None) or getattr(data, "holdings", None) or []

        holdings = []
        for position in positions:
            if isinstance(position, dict):
                symbol_data = position.get("symbol", {})
                symbol = self._extract_symbol(symbol_data)
                units = float(position.get("units", 0) or 0)
                price = float(position.get("price", 0) or 0)
                currency = self._extract_currency(symbol_data)
                avg_price_raw = position.get("average_purchase_price")
                raw_data = position
            else:
                symbol_data = getattr(position, "symbol", None)
                symbol = self._extract_symbol(symbol_data)
                units = float(getattr(position, "units", 0) or 0)
                price = float(getattr(position, "price", 0) or 0)
                currency = self._extract_currency(symbol_data)
                avg_price_raw = getattr(position, "average_purchase_price", None)
                raw_data = self._to_dict(position)

            avg_price = float(avg_price_raw) if avg_price_raw is not None else None

            holdings.append(
                SnapTradeHolding(
                    account_id=account_id,
                    symbol=symbol,
                    quantity=units,
                    price=price,
                    market_value=units * price,
                    currency=currency,
                    average_purchase_price=avg_price,
                    raw_data=raw_data,
                )
            )

        # Extract cash balances from the response
        cash_holdings = self._extract_cash_balances(data, account_id)
        holdings.extend(cash_holdings)

        return holdings

    def _extract_cash_balances(self, data, account_id: str) -> list[SnapTradeHolding]:
        """Extract cash balances from the holdings API response.

        The get_user_holdings response includes a 'balances' array alongside
        'positions'. Each balance entry has currency.code and cash fields.

        Args:
            data: The raw API response (dict or SDK object).
            account_id: The account these balances belong to.

        Returns:
            List of SnapTradeHolding objects for non-zero cash balances.
        """
        # Extract balances array from the response
        if isinstance(data, dict):
            balances = data.get("balances") or []
        elif isinstance(data, list):
            # Direct list of positions has no balances
            return []
        else:
            balances = getattr(data, "balances", None) or []

        cash_holdings = []
        for balance in balances:
            if isinstance(balance, dict):
                cash_amount = float(balance.get("cash", 0) or 0)
                currency_data = balance.get("currency", {})
                if isinstance(currency_data, dict):
                    currency_code = currency_data.get("code", "USD")
                elif isinstance(currency_data, str):
                    currency_code = currency_data
                else:
                    currency_code = getattr(currency_data, "code", "USD")
            else:
                cash_amount = float(getattr(balance, "cash", 0) or 0)
                currency_data = getattr(balance, "currency", None)
                if currency_data is None:
                    currency_code = "USD"
                elif isinstance(currency_data, dict):
                    currency_code = currency_data.get("code", "USD")
                elif isinstance(currency_data, str):
                    currency_code = currency_data
                else:
                    currency_code = getattr(currency_data, "code", "USD")

            if cash_amount == 0:
                continue

            cash_holdings.append(
                SnapTradeHolding(
                    account_id=account_id,
                    symbol=f"_CASH:{currency_code}",
                    quantity=cash_amount,
                    price=1.0,
                    market_value=cash_amount,
                    currency=currency_code,
                )
            )

        return cash_holdings

    def _extract_last_successful_sync(self, account_data) -> datetime | None:
        """Extract last_successful_sync from a raw SnapTrade account object.

        Path: account.sync_status.holdings.last_successful_sync

        Args:
            account_data: A single raw account (dict or SDK object)

        Returns:
            A timezone-aware datetime, or None if not available.
        """
        # Navigate: account_data -> sync_status -> holdings -> last_successful_sync
        if isinstance(account_data, dict):
            sync_status = account_data.get("sync_status")
        else:
            sync_status = getattr(account_data, "sync_status", None)

        if sync_status is None:
            return None

        if isinstance(sync_status, dict):
            holdings_meta = sync_status.get("holdings")
        else:
            holdings_meta = getattr(sync_status, "holdings", None)

        if holdings_meta is None:
            return None

        if isinstance(holdings_meta, dict):
            sync_str = holdings_meta.get("last_successful_sync")
        else:
            sync_str = getattr(holdings_meta, "last_successful_sync", None)

        if not sync_str:
            return None

        return parse_iso_datetime(sync_str)

    def get_activities(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> list[ProviderActivity]:
        """Fetch activities/transactions from SnapTrade.

        Args:
            start_date: Start of date range (defaults to 90 days ago).
            end_date: End of date range (defaults to today).

        Returns:
            List of ProviderActivity objects.
        """
        self._check_credentials()

        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=90)

        response = self.client.transactions_and_reporting.get_activities(
            user_id=self.user_id,
            user_secret=self.user_secret,
            start_date=str(start_date),
            end_date=str(end_date),
        )

        raw_activities = response if isinstance(response, list) else response.body

        activities = []
        for raw in raw_activities:
            activity = self._map_snaptrade_activity(raw)
            if activity:
                activities.append(activity)

        return activities

    def _map_snaptrade_activity(self, raw) -> ProviderActivity | None:
        """Map a single SnapTrade activity to ProviderActivity.

        Handles both dict and SDK object response formats.

        Args:
            raw: A single raw activity (dict or SDK object).

        Returns:
            ProviderActivity or None if the activity can't be mapped.
        """
        if isinstance(raw, dict):
            external_id = str(raw.get("id", ""))
            account_id = self._extract_nested_id(raw.get("account")) or str(raw.get("account_id", ""))
            activity_type = raw.get("type", "unknown")
            description = raw.get("description", "")
            trade_date_str = raw.get("trade_date")
            settlement_date_str = raw.get("settlement_date")
            symbol_data = raw.get("symbol")
            units_raw = raw.get("units")
            price_raw = raw.get("price")
            amount_raw = raw.get("amount")
            fee_raw = raw.get("fee") or raw.get("commission")
            currency = self._extract_activity_currency(raw)
        else:
            external_id = str(getattr(raw, "id", ""))
            account_id = self._extract_nested_id(getattr(raw, "account", None)) or str(getattr(raw, "account_id", ""))
            activity_type = getattr(raw, "type", "unknown")
            description = getattr(raw, "description", "")
            trade_date_str = getattr(raw, "trade_date", None)
            settlement_date_str = getattr(raw, "settlement_date", None)
            symbol_data = getattr(raw, "symbol", None)
            units_raw = getattr(raw, "units", None)
            price_raw = getattr(raw, "price", None)
            amount_raw = getattr(raw, "amount", None)
            fee_raw = getattr(raw, "fee", None) or getattr(raw, "commission", None)
            currency = self._extract_activity_currency(raw)

        if not external_id:
            return None

        activity_date = parse_iso_datetime(trade_date_str)
        if not activity_date:
            return None

        settlement_date = parse_iso_datetime(settlement_date_str)
        ticker = self._extract_symbol(symbol_data) if symbol_data else None
        if ticker == "UNKNOWN":
            ticker = None

        units = Decimal(str(units_raw)) if units_raw is not None else None
        price = Decimal(str(price_raw)) if price_raw is not None else None
        amount = Decimal(str(amount_raw)) if amount_raw is not None else None
        fee = Decimal(str(fee_raw)) if fee_raw is not None else None

        return ProviderActivity(
            account_id=account_id,
            external_id=external_id,
            activity_date=activity_date,
            type=str(activity_type).lower() if activity_type else "unknown",
            description=description,
            settlement_date=settlement_date,
            ticker=ticker,
            units=units,
            price=price,
            amount=amount,
            currency=currency,
            fee=fee,
            raw_data=self._to_dict(raw),
        )

    def _extract_nested_id(self, obj) -> str | None:
        """Extract an ID from a nested object (dict or SDK object).

        SnapTrade often nests account as {"id": "..."} or an object with .id.

        Args:
            obj: A dict, SDK object, or string.

        Returns:
            The extracted ID string, or None.
        """
        if obj is None:
            return None
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            return str(obj.get("id", "")) or None
        val = getattr(obj, "id", None)
        return str(val) if val else None

    def _extract_activity_currency(self, raw) -> str:
        """Extract currency from a SnapTrade activity.

        Args:
            raw: A single raw activity (dict or SDK object).

        Returns:
            Currency code string (defaults to "USD").
        """
        if isinstance(raw, dict):
            currency = raw.get("currency")
            if isinstance(currency, dict):
                return currency.get("code", "USD")
            if isinstance(currency, str):
                return currency
            # Try from symbol
            symbol_data = raw.get("symbol")
            if symbol_data:
                return self._extract_currency(symbol_data)
            return "USD"
        else:
            currency = getattr(raw, "currency", None)
            if isinstance(currency, dict):
                return currency.get("code", "USD")
            if isinstance(currency, str):
                return currency
            symbol_data = getattr(raw, "symbol", None)
            if symbol_data:
                return self._extract_currency(symbol_data)
            return "USD"

    def _to_dict(self, obj) -> dict:
        """Convert an SDK object or dict to a plain dict for raw_data storage.

        Args:
            obj: A dict, SDK object, or other value.

        Returns:
            A plain dict.
        """
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return {"value": str(obj)}

    def sync_all(self) -> ProviderSyncResult:
        """Fetch all holdings, accounts, activities, and balance dates from SnapTrade.

        Reads last_successful_sync from the account list response
        (account.sync_status.holdings.last_successful_sync), then
        delegates to get_holdings() for position data and get_activities()
        for transaction data.

        Returns:
            ProviderSyncResult with holdings, accounts, activities, empty errors,
            and per-account balance_dates from last_successful_sync.
        """
        self._check_credentials()
        logger.info("SnapTrade: fetching accounts and holdings")

        # Fetch raw account list to extract sync_status metadata and account info
        response = self.client.account_information.list_user_accounts(
            user_id=self.user_id,
            user_secret=self.user_secret,
        )
        raw_accounts = response if isinstance(response, list) else response.body

        accounts: list[ProviderAccount] = []
        balance_dates: dict[str, datetime | None] = {}
        for raw_account in raw_accounts:
            if isinstance(raw_account, dict):
                acc_id = str(raw_account.get("id", ""))
                name = raw_account.get("name") or "Unknown Account"
                institution = raw_account.get("institution_name") or self._extract_brokerage_name(
                    raw_account.get("brokerage_authorization")
                )
                account_number = raw_account.get("number")
            else:
                acc_id = str(getattr(raw_account, "id", ""))
                name = getattr(raw_account, "name", None) or "Unknown Account"
                institution = getattr(raw_account, "institution_name", None) or self._extract_brokerage_name(
                    getattr(raw_account, "brokerage_authorization", None)
                )
                account_number = getattr(raw_account, "number", None)

            accounts.append(
                ProviderAccount(
                    id=acc_id,
                    name=name,
                    institution=institution,
                    account_number=account_number,
                )
            )
            balance_dates[acc_id] = self._extract_last_successful_sync(raw_account)

        # Use existing get_holdings() for position data
        holdings = self.get_holdings()

        # Fetch activities (best-effort — don't fail the sync)
        activities: list[ProviderActivity] = []
        try:
            activities = self.get_activities()
        except Exception:
            logger.debug("SnapTrade: activity fetch failed", exc_info=True)

        logger.info(
            "SnapTrade: %d accounts, %d holdings, %d activities fetched",
            len(accounts), len(holdings), len(activities),
        )

        return ProviderSyncResult(
            holdings=holdings,
            accounts=accounts,
            errors=[],
            balance_dates=balance_dates,
            activities=activities,
        )

    # -------------------------------------------------------------------------
    # ProviderClient protocol implementation
    # -------------------------------------------------------------------------

    def get_provider_accounts(self) -> list[ProviderAccount]:
        """Fetch accounts in normalized ProviderAccount format.

        This method implements the ProviderClient protocol.

        Returns:
            List of ProviderAccount objects.
        """
        snaptrade_accounts = self.get_accounts()
        return [
            ProviderAccount(
                id=acc.id,
                name=acc.name,
                institution=acc.brokerage_name,
                account_number=acc.account_number,
            )
            for acc in snaptrade_accounts
        ]

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Fetch holdings in normalized ProviderHolding format.

        This method implements the ProviderClient protocol.

        Args:
            account_id: If provided, fetch holdings only for this account.
                       If None, fetch holdings for all accounts.

        Returns:
            List of ProviderHolding objects.
        """
        if account_id:
            snaptrade_holdings = self._get_holdings_for_account(account_id)
        else:
            snaptrade_holdings = self.get_all_holdings()

        return [
            ProviderHolding(
                account_id=h.account_id,
                symbol=h.symbol,
                quantity=Decimal(str(h.quantity)),
                price=Decimal(str(h.price)),
                market_value=Decimal(str(h.market_value)),
                currency=h.currency,
                name=None,  # SnapTrade doesn't provide security name in holdings
                cost_basis=Decimal(str(h.average_purchase_price)) if h.average_purchase_price and h.average_purchase_price > 0 else None,
                raw_data=h.raw_data,
            )
            for h in snaptrade_holdings
        ]
