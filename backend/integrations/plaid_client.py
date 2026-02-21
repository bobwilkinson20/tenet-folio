"""Plaid API client.

This module implements the ProviderClient protocol for Plaid integration
via the plaid-python SDK, fetching investment holdings, accounts, and
transaction history.

Unlike other providers, Plaid uses per-institution access tokens (Items).
The sync_all() method loads access tokens from the PlaidItem DB table
internally, keeping the sync service free of provider-specific logic.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from plaid import ApiException, Environment
from plaid.api.plaid_api import PlaidApi
from plaid.api_client import ApiClient
from plaid.configuration import Configuration
from plaid.model.country_code import CountryCode
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.investments_transactions_get_request import InvestmentsTransactionsGetRequest
from plaid.model.investments_transactions_get_request_options import InvestmentsTransactionsGetRequestOptions
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from config import settings
from integrations.provider_protocol import (
    ErrorCategory,
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncError,
    ProviderSyncResult,
)

logger = logging.getLogger(__name__)

# Map PLAID_ENVIRONMENT setting to SDK host URLs.
# Plaid's Development environment is deprecated; only sandbox and production
# are supported.
_ENVIRONMENT_MAP: dict[str, str] = {
    "sandbox": Environment.Sandbox,
    "production": Environment.Production,
}


def _generate_plaid_synthetic_symbol(security_id: str) -> str:
    """Generate a deterministic synthetic ticker for Plaid holdings without a symbol.

    Args:
        security_id: The Plaid security_id for the holding.

    Returns:
        A synthetic ticker in the format ``_PLAID:{hash8}``.
    """
    h = hashlib.sha256(security_id.encode()).hexdigest()[:8]
    return f"_PLAID:{h}"


class PlaidClient:
    """Wrapper around the Plaid API.

    Implements the ProviderClient protocol for multi-provider support.
    Uses the plaid-python SDK to fetch investment data.
    """

    def __init__(
        self,
        client_id: str | None = None,
        secret: str | None = None,
        environment: str | None = None,
    ):
        self._client_id = client_id or settings.PLAID_CLIENT_ID
        self._secret = secret or settings.PLAID_SECRET
        self._environment = environment or settings.PLAID_ENVIRONMENT

        # Lazily created on first use
        self._api: PlaidApi | None = None

    def _get_api(self) -> PlaidApi:
        """Return (and cache) a PlaidApi instance."""
        if self._api is None:
            env_key = self._environment.lower()
            host = _ENVIRONMENT_MAP.get(env_key)
            if host is None:
                logger.warning(
                    "Unknown PLAID_ENVIRONMENT=%r, falling back to sandbox. "
                    "Valid values: sandbox, production",
                    self._environment,
                )
                host = Environment.Sandbox
            logger.info(
                "Plaid API client: environment=%s, host=%s, client_id=<configured>",
                env_key,
                host,
            )
            configuration = Configuration(
                host=host,
                api_key={
                    "clientId": self._client_id,
                    "secret": self._secret,
                },
            )
            api_client = ApiClient(configuration)
            self._api = PlaidApi(api_client)
        return self._api

    @property
    def provider_name(self) -> str:
        """Return the provider name for database storage."""
        return "Plaid"

    def is_configured(self) -> bool:
        """Check if Plaid credentials are configured."""
        return bool(self._client_id) and bool(self._secret)

    # ------------------------------------------------------------------
    # Link Token & Token Exchange (used by API routes, not sync)
    # ------------------------------------------------------------------

    def create_link_token(self) -> str:
        """Create a Plaid Link token for the browser-based auth flow.

        Returns:
            The link_token string to be passed to Plaid Link.
        """
        api = self._get_api()
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id="tenet-folio-user"),
            client_name="TenetFolio",
            products=[Products("investments")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        response = api.link_token_create(request)
        return response["link_token"]

    def exchange_public_token(self, public_token: str) -> dict:
        """Exchange a Plaid Link public_token for a permanent access_token.

        Args:
            public_token: The public_token from Plaid Link on-success callback.

        Returns:
            Dict with ``access_token`` and ``item_id``.
        """
        api = self._get_api()
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = api.item_public_token_exchange(request)
        return {
            "access_token": response["access_token"],
            "item_id": response["item_id"],
        }

    def remove_item(self, access_token: str) -> None:
        """Revoke an access token by calling Plaid's /item/remove endpoint.

        Args:
            access_token: The Item's access token to revoke.
        """
        api = self._get_api()
        api.item_remove(ItemRemoveRequest(access_token=access_token))

    # ------------------------------------------------------------------
    # ProviderClient protocol — accounts & holdings
    # ------------------------------------------------------------------

    def get_accounts(self) -> list[ProviderAccount]:
        """Not directly supported — accounts are discovered during sync_all."""
        return []

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Not directly supported — holdings are fetched during sync_all."""
        return []

    # ------------------------------------------------------------------
    # sync_all
    # ------------------------------------------------------------------

    def _load_access_tokens(self) -> list[tuple[str, str]]:
        """Load access tokens from the PlaidItem DB table.

        Returns:
            List of ``(access_token, institution_name)`` tuples.
        """
        from database import get_db
        from models.plaid_item import PlaidItem

        db = next(get_db())
        try:
            plaid_items = db.query(PlaidItem).all()
            return [
                (item.access_token, item.institution_name or "Unknown")
                for item in plaid_items
            ]
        finally:
            db.close()

    def sync_all(self) -> ProviderSyncResult:
        """Fetch all data from Plaid across all linked Items.

        Loads access tokens from the PlaidItem DB table internally,
        keeping the sync_service free of provider-specific logic.

        Returns:
            ProviderSyncResult with holdings, accounts, activities, and errors.
        """
        access_tokens = self._load_access_tokens()

        if not access_tokens:
            return ProviderSyncResult(holdings=[], accounts=[], errors=[], activities=[])

        api = self._get_api()
        all_holdings: list[ProviderHolding] = []
        all_accounts: list[ProviderAccount] = []
        all_activities: list[ProviderActivity] = []
        errors: list[ProviderSyncError] = []
        balance_dates: dict[str, datetime | None] = {}

        now = datetime.now(timezone.utc)

        for access_token, institution_name in access_tokens:
            try:
                holdings, accounts = self._fetch_item_holdings(
                    api, access_token, institution_name
                )
                all_holdings.extend(holdings)
                all_accounts.extend(accounts)
                for acct in accounts:
                    balance_dates[acct.id] = now
            except ApiException as e:
                errors.append(self._map_plaid_error(e, institution_name))
            except Exception as e:
                errors.append(ProviderSyncError(
                    message=f"Failed to fetch holdings from {institution_name}: {e}",
                    category=ErrorCategory.UNKNOWN,
                    institution_name=institution_name,
                ))

            try:
                activities = self._fetch_item_activities(api, access_token)
                all_activities.extend(activities)
            except ApiException as e:
                logger.warning(
                    "Failed to fetch activities from %s: %s",
                    institution_name, e,
                )
            except Exception:
                logger.warning(
                    "Failed to fetch activities from %s",
                    institution_name, exc_info=True,
                )

        logger.info(
            "Plaid: %d accounts, %d holdings, %d activities fetched",
            len(all_accounts), len(all_holdings), len(all_activities),
        )

        return ProviderSyncResult(
            holdings=all_holdings,
            accounts=all_accounts,
            errors=errors,
            balance_dates=balance_dates,
            activities=all_activities,
        )

    # ------------------------------------------------------------------
    # Internal: fetch holdings for a single Item
    # ------------------------------------------------------------------

    def _fetch_item_holdings(
        self,
        api: PlaidApi,
        access_token: str,
        institution_name: str,
    ) -> tuple[list[ProviderHolding], list[ProviderAccount]]:
        """Fetch holdings and accounts for a single Plaid Item.

        Returns:
            Tuple of (holdings, accounts).
        """
        request = InvestmentsHoldingsGetRequest(access_token=access_token)
        response = api.investments_holdings_get(request)

        # Build security lookup: security_id -> security dict
        securities_map: dict[str, dict] = {}
        for sec in response.get("securities", []) or []:
            sid = sec.get("security_id")
            if sid:
                securities_map[sid] = sec

        # Map accounts
        accounts: list[ProviderAccount] = []
        account_ids: set[str] = set()
        for acct in response.get("accounts", []) or []:
            acct_id = acct.get("account_id", "")
            if acct_id:
                account_ids.add(acct_id)
                accounts.append(ProviderAccount(
                    id=acct_id,
                    name=acct.get("name") or acct.get("official_name") or "Plaid Account",
                    institution=institution_name,
                    account_number=acct.get("mask"),
                ))

        # Map holdings
        holdings: list[ProviderHolding] = []
        for h in response.get("holdings", []) or []:
            holding = self._map_holding(h, securities_map)
            if holding:
                holdings.append(holding)

        return holdings, accounts

    def _map_holding(
        self,
        holding: dict,
        securities_map: dict[str, dict],
    ) -> ProviderHolding | None:
        """Map a single Plaid holding to a ProviderHolding."""
        account_id = holding.get("account_id", "")
        security_id = holding.get("security_id", "")
        security = securities_map.get(security_id, {})

        quantity = self._to_decimal(holding.get("quantity"))
        if quantity is None or quantity == 0:
            return None

        # Currency
        currency = (
            holding.get("iso_currency_code")
            or security.get("iso_currency_code")
            or "USD"
        ).upper()

        # Detect cash securities (e.g. ticker "CUR:USD" with type "cash").
        # Only use the explicit type field — is_cash_equivalent is unreliable
        # (some institutions flag crypto as cash equivalent).
        sec_type = str(security.get("type") or "").lower()
        if sec_type == "cash":
            return ProviderHolding(
                account_id=account_id,
                symbol=f"_CASH:{currency}",
                quantity=quantity,
                price=Decimal("1"),
                market_value=quantity,
                currency=currency,
                name=f"{currency} Cash",
            )

        price = self._to_decimal(holding.get("institution_price")) or Decimal("0")
        market_value = self._to_decimal(holding.get("institution_value")) or Decimal("0")

        # Symbol: use ticker_symbol from the security, or generate synthetic
        symbol = security.get("ticker_symbol")
        if not symbol:
            if security_id:
                symbol = _generate_plaid_synthetic_symbol(security_id)
            else:
                return None

        name = security.get("name")

        # Cost basis: Plaid provides total cost_basis, convert to per-unit
        cost_basis: Decimal | None = None
        total_cost = self._to_decimal(holding.get("cost_basis"))
        if total_cost is not None and quantity and quantity != 0:
            cost_basis = total_cost / abs(quantity)

        return ProviderHolding(
            account_id=account_id,
            symbol=symbol,
            quantity=quantity,
            price=price,
            market_value=market_value,
            currency=currency,
            name=name,
            cost_basis=cost_basis,
        )

    # ------------------------------------------------------------------
    # Internal: fetch activities for a single Item
    # ------------------------------------------------------------------

    def _fetch_item_activities(
        self,
        api: PlaidApi,
        access_token: str,
        days: int = 730,
    ) -> list[ProviderActivity]:
        """Fetch investment transactions for a single Item with pagination.

        Args:
            api: The PlaidApi instance.
            access_token: The Item's access token.
            days: Number of days of history (default 730 = ~24 months).

        Returns:
            List of ProviderActivity objects.
        """
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)

        request = InvestmentsTransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
        )

        activities: list[ProviderActivity] = []
        total_transactions = None
        offset = 0

        while True:
            response = api.investments_transactions_get(request)

            if total_transactions is None:
                total_transactions = response.get("total_investment_transactions", 0)

            # Build security lookup for this response
            securities_map: dict[str, dict] = {}
            for sec in response.get("securities", []) or []:
                sid = sec.get("security_id")
                if sid:
                    securities_map[sid] = sec

            for txn in response.get("investment_transactions", []) or []:
                activity = self._map_transaction(txn, securities_map)
                if activity:
                    activities.append(activity)

            offset += len(response.get("investment_transactions", []) or [])
            if offset >= total_transactions:
                break

            # Request next page
            request = InvestmentsTransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=InvestmentsTransactionsGetRequestOptions(offset=offset),
            )

        return activities

    def _map_transaction(
        self,
        txn: dict,
        securities_map: dict[str, dict],
    ) -> ProviderActivity | None:
        """Map a Plaid investment transaction to a ProviderActivity.

        Plaid sign convention: positive amount = cash outflow (purchase).
        Our convention: buys are negative amounts, sells are positive.
        So we flip the sign.
        """
        external_id = txn.get("investment_transaction_id", "")
        if not external_id:
            return None

        account_id = txn.get("account_id", "")

        # Date
        txn_date = txn.get("date")
        if txn_date is None:
            return None
        if isinstance(txn_date, datetime):
            activity_date = txn_date if txn_date.tzinfo else txn_date.replace(tzinfo=timezone.utc)
        elif hasattr(txn_date, "year"):
            # date object
            activity_date = datetime(txn_date.year, txn_date.month, txn_date.day, tzinfo=timezone.utc)
        else:
            try:
                from integrations.parsing_utils import parse_iso_datetime
                activity_date = parse_iso_datetime(txn_date)
                if activity_date is None:
                    return None
            except Exception:
                return None

        # Type mapping
        txn_type = str(txn.get("type") or "").lower()
        txn_subtype = str(txn.get("subtype") or "").lower()
        activity_type = self._map_activity_type(txn_type, txn_subtype)

        # Amount — flip sign (Plaid positive = outflow, we want buys negative)
        raw_amount = self._to_decimal(txn.get("amount"))
        amount = -raw_amount if raw_amount is not None else None

        # Quantity
        quantity = self._to_decimal(txn.get("quantity"))

        # Price
        price = self._to_decimal(txn.get("price"))

        # Security info
        security_id = txn.get("security_id", "")
        security = securities_map.get(security_id, {})
        ticker = security.get("ticker_symbol")

        # Currency
        currency = (txn.get("iso_currency_code") or "USD").upper()

        # Fees
        fees = self._to_decimal(txn.get("fees"))

        # Description
        name = txn.get("name") or security.get("name") or ""
        description = name or f"{activity_type.upper()} on Plaid"

        return ProviderActivity(
            account_id=account_id,
            external_id=external_id,
            activity_date=activity_date,
            type=activity_type,
            amount=amount,
            description=description,
            ticker=ticker,
            units=quantity,
            price=price,
            currency=currency,
            fee=fees,
        )

    @staticmethod
    def _map_activity_type(txn_type: str, txn_subtype: str) -> str:
        """Map Plaid transaction type/subtype to our activity type."""
        if txn_type == "buy":
            return "buy"
        if txn_type == "sell":
            return "sell"
        if txn_type == "cash" and txn_subtype == "dividend":
            return "dividend"
        if txn_type == "cash" and txn_subtype == "interest":
            return "interest"
        if txn_type == "cash" and txn_subtype in ("deposit", "contribution"):
            return "deposit"
        if txn_type == "cash" and txn_subtype in ("withdrawal", "distribution"):
            return "withdrawal"
        if txn_type == "transfer":
            return "transfer"
        if txn_type == "fee":
            return "fee"
        return "other"

    # ------------------------------------------------------------------
    # Error mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_plaid_error(
        exc: ApiException,
        institution_name: str | None = None,
    ) -> ProviderSyncError:
        """Map a Plaid ApiException to a ProviderSyncError."""
        status = exc.status or 0
        message = str(exc)

        # Try to extract error_code from the body
        error_code = ""
        try:
            body = json.loads(exc.body) if exc.body else {}
            error_code = body.get("error_code", "")
            error_message = body.get("error_message", "")
            if error_message:
                message = f"Plaid error ({error_code}): {error_message}"
        except Exception:
            pass

        if status in (401, 403) or error_code in (
            "INVALID_ACCESS_TOKEN",
            "ITEM_LOGIN_REQUIRED",
        ):
            category = ErrorCategory.AUTH
        elif status == 429:
            category = ErrorCategory.RATE_LIMIT
        elif status >= 500:
            category = ErrorCategory.CONNECTION
        else:
            category = ErrorCategory.UNKNOWN

        return ProviderSyncError(
            message=message,
            category=category,
            institution_name=institution_name,
            retriable=category in (ErrorCategory.RATE_LIMIT, ErrorCategory.CONNECTION),
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
