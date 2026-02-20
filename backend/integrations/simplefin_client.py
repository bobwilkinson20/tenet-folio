"""SimpleFIN API client wrapper.

This module implements the ProviderClient protocol for SimpleFIN integration.
SimpleFIN is a protocol for sharing read-only financial data, and SimpleFIN Bridge
is a service that connects to banks and brokerages.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from decimal import Decimal

import httpx

from config import settings
from integrations.exceptions import (
    ProviderAPIError,
    ProviderAuthError,
    ProviderConnectionError,
)
from integrations.parsing_utils import parse_unix_timestamp
from integrations.provider_protocol import (
    ErrorCategory,
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncError,
    ProviderSyncResult,
)

logger = logging.getLogger(__name__)


# Symbols that represent cash positions, not tradable securities.
# Brokerages like Altruist report cash as a holding with symbol "$".
_CASH_SYMBOLS = frozenset({
    "$", "$$",
    "usd", "eur", "gbp", "cad", "aud", "jpy", "chf", "nzd", "hkd", "sgd",
    "cash", "cash & cash equivalents",
})


def _is_cash_symbol(symbol: str) -> bool:
    """Check if a holding symbol represents a cash position.

    Args:
        symbol: The holding symbol to check.

    Returns:
        True if the symbol is a known cash-like identifier.
    """
    return symbol.lower().strip() in _CASH_SYMBOLS


def _generate_synthetic_symbol(holding_id: str) -> str:
    """Generate stable synthetic symbol for holdings without tickers.

    Args:
        holding_id: The SimpleFIN holding ID

    Returns:
        A synthetic symbol in format _SF:{8-char-hash}
    """
    hash_hex = hashlib.sha256(holding_id.encode()).hexdigest()
    return f"_SF:{hash_hex[:8]}"


class SimpleFINClient:
    """Wrapper around the SimpleFIN API.

    Implements the ProviderClient protocol for multi-provider support.

    Note: We make direct HTTP requests rather than using the simplefin library
    because we need access to holdings data which requires fetching without
    the balances-only flag.
    """

    # Cache TTL - SimpleFIN has a 24 request/day limit, so cache aggressively
    _CACHE_TTL = timedelta(minutes=5)

    def __init__(self, access_url: str | None = None):
        """Initialize the client with credentials.

        Args:
            access_url: SimpleFIN access URL (defaults to settings)
        """
        self._access_url = access_url or settings.SIMPLEFIN_ACCESS_URL
        self._cache: dict | None = None
        self._cache_time: datetime | None = None

    @property
    def provider_name(self) -> str:
        """Return the provider name for database storage."""
        return "SimpleFIN"

    def is_configured(self) -> bool:
        """Check if SimpleFIN credentials are configured.

        Returns:
            True if access URL is present and valid, False otherwise.
        """
        if not self._access_url:
            return False
        # Must be a URL, not a base64 setup token
        return self._access_url.startswith(("http://", "https://"))

    def _check_credentials(self) -> None:
        """Raise an error if credentials are not configured or invalid."""
        if not self._access_url:
            raise ProviderAuthError(
                "SimpleFIN credentials not configured. "
                "Run 'python scripts/setup_simplefin.py' to set up SimpleFIN.",
                provider_name="SimpleFIN",
            )
        # Check if user accidentally put the setup token instead of access URL
        if not self._access_url.startswith(("http://", "https://")):
            raise ProviderAuthError(
                "SIMPLEFIN_ACCESS_URL appears to be a setup token (base64), not an access URL. "
                "Run 'python scripts/setup_simplefin.py' to exchange the setup token for an access URL.",
                provider_name="SimpleFIN",
            )

    def _fetch_data(self) -> dict:
        """Fetch data from SimpleFIN with caching.

        SimpleFIN has a 24 request/day limit, so we cache responses
        for a short period to avoid unnecessary API calls.

        Includes date range parameters so the response contains
        transactions alongside holdings.

        Returns:
            Dict with 'accounts' key containing list of account data.
        """
        self._check_credentials()

        # Check cache
        now = datetime.now()
        if (
            self._cache is not None
            and self._cache_time is not None
            and (now - self._cache_time) < self._CACHE_TTL
        ):
            logger.debug("SimpleFIN: using cached data")
            return self._cache

        # Request the last 90 days of transactions alongside holdings.
        # Without start-date, SimpleFIN may omit the transactions array.
        start_date = now - timedelta(days=90)
        params = {
            "start-date": str(int(start_date.timestamp())),
        }

        try:
            with httpx.Client(base_url=self._access_url, timeout=30) as client:
                response = client.get("/accounts", params=params)
                response.raise_for_status()
                self._cache = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise ProviderAuthError(
                    f"SimpleFIN authentication failed (HTTP {status})",
                    provider_name="SimpleFIN",
                ) from exc
            raise ProviderAPIError(
                f"SimpleFIN API error (HTTP {status})",
                provider_name="SimpleFIN",
                status_code=status,
            ) from exc
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderConnectionError(
                f"SimpleFIN connection failed: {exc}",
                provider_name="SimpleFIN",
            ) from exc

        self._cache_time = now
        account_count = len(self._cache.get("accounts", []))
        logger.info("SimpleFIN: data fetched (%d accounts)", account_count)
        return self._cache

    def get_accounts(self) -> list[ProviderAccount]:
        """Fetch all accounts from SimpleFIN.

        Returns:
            List of ProviderAccount objects.
        """
        data = self._fetch_data()
        accounts_data = data.get("accounts", [])

        accounts = []
        for sf_account in accounts_data:
            # Extract institution name from org object
            institution = "Unknown"
            org = sf_account.get("org")
            if org:
                institution = org.get("name", "Unknown")

            accounts.append(
                ProviderAccount(
                    id=sf_account.get("id", ""),
                    name=sf_account.get("name") or "Unnamed Account",
                    institution=institution,
                    account_number=None,  # SimpleFIN doesn't expose account numbers
                )
            )

        return accounts

    # Alias for ProviderClient protocol compatibility
    def get_provider_accounts(self) -> list[ProviderAccount]:
        """Alias for get_accounts() for protocol compatibility."""
        return self.get_accounts()

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Fetch holdings from SimpleFIN.

        Args:
            account_id: If provided, fetch holdings only for this account.
                       If None, fetch holdings for all accounts.

        Returns:
            List of ProviderHolding objects.
        """
        data = self._fetch_data()
        accounts_data = data.get("accounts", [])

        holdings = []
        for sf_account in accounts_data:
            acct_id = sf_account.get("id", "")

            # Filter by account if specified
            if account_id and acct_id != account_id:
                continue

            # Process holdings for this account
            account_holdings_list = []
            raw_holdings = sf_account.get("holdings") or []
            for sf_holding in raw_holdings:
                holding = self._map_holding(sf_holding, acct_id)
                if holding:
                    account_holdings_list.append(holding)

            holdings.extend(account_holdings_list)

            # Derive cash holding from balance minus holdings total
            cash_holding = self._derive_cash_holding(sf_account, account_holdings_list)
            if cash_holding:
                holdings.append(cash_holding)

        return holdings

    def _derive_cash_holding(
        self, sf_account: dict, account_holdings: list[ProviderHolding]
    ) -> ProviderHolding | None:
        """Derive a cash holding from account balance minus holdings total.

        SimpleFIN provides total account balance. Cash is the difference
        between the balance and the sum of holdings market values.

        Args:
            sf_account: SimpleFIN account dict with balance field.
            account_holdings: Already-mapped holdings for this account.

        Returns:
            A ProviderHolding for cash, or None if balance is missing or cash is zero.
        """
        balance_raw = sf_account.get("balance")
        if balance_raw is None:
            return None

        try:
            balance = Decimal(str(balance_raw))
        except Exception:
            return None

        holdings_total = sum(h.market_value for h in account_holdings)
        cash = balance - holdings_total

        if cash == 0:
            return None

        currency = sf_account.get("currency", "USD") or "USD"
        acct_id = sf_account.get("id", "")

        return ProviderHolding(
            account_id=acct_id,
            symbol=f"_CASH:{currency}",
            quantity=cash,
            price=Decimal("1"),
            market_value=cash,
            currency=currency,
            name=f"{currency} Cash",
        )

    def _map_holding(self, sf_holding: dict, account_id: str) -> ProviderHolding | None:
        """Map a SimpleFIN holding to ProviderHolding.

        Args:
            sf_holding: SimpleFIN holding dict
            account_id: The account ID this holding belongs to

        Returns:
            ProviderHolding or None if the holding can't be mapped
        """
        # Extract symbol, or generate synthetic symbol for holdings without one
        symbol = sf_holding.get("symbol")
        if symbol and _is_cash_symbol(symbol):
            # Cash positions reported as holdings (e.g. "$" from Altruist)
            # are skipped so _derive_cash_holding handles them via balance math.
            logger.debug("SimpleFIN: skipping cash-like holding symbol=%r", symbol)
            return None
        if not symbol:
            holding_id = sf_holding.get("id")
            if not holding_id:
                # Cannot create stable symbol without ID
                return None
            # Skip zero-value holdings without symbols (SimpleFIN includes many extraneous ones)
            market_value_raw = sf_holding.get("market_value", 0)
            if not market_value_raw or Decimal(str(market_value_raw)) <= 0:
                return None
            symbol = _generate_synthetic_symbol(holding_id)

        # Extract quantity (SimpleFIN uses "shares" field, which may be a string)
        shares_raw = sf_holding.get("shares", 0)
        quantity = Decimal(str(shares_raw)) if shares_raw else Decimal(0)

        # Extract market value
        market_value_raw = sf_holding.get("market_value", 0)
        market_value = Decimal(str(market_value_raw)) if market_value_raw else Decimal(0)

        # Calculate or extract price
        # SimpleFIN may provide purchase_price but not current price
        # Calculate from market_value / quantity if possible
        price = Decimal(0)
        if quantity and quantity > 0 and market_value:
            price = market_value / quantity
        else:
            # Fall back to purchase_price if available
            purchase_price = sf_holding.get("purchase_price")
            if purchase_price:
                price = Decimal(str(purchase_price))

        # Extract currency
        currency = sf_holding.get("currency", "USD") or "USD"

        # Extract description/name
        name = sf_holding.get("description")

        # Extract per-unit cost basis
        unit_cost: Decimal | None = None
        purchase_price_raw = sf_holding.get("purchase_price")
        if purchase_price_raw:
            try:
                pp = Decimal(str(purchase_price_raw))
                if pp > 0:
                    unit_cost = pp
            except Exception:
                pass
        if unit_cost is None:
            # Fall back to total cost_basis / quantity
            cost_basis_raw = sf_holding.get("cost_basis")
            if cost_basis_raw and quantity and quantity > 0:
                try:
                    total_cost = Decimal(str(cost_basis_raw))
                    if total_cost > 0:
                        unit_cost = total_cost / quantity
                except Exception:
                    pass

        return ProviderHolding(
            account_id=account_id,
            symbol=symbol,
            quantity=quantity,
            price=price,
            market_value=market_value,
            currency=currency,
            name=name,
            cost_basis=unit_cost,
            raw_data=sf_holding,
        )

    def get_activities(self, account_id: str | None = None) -> list[ProviderActivity]:
        """Fetch activities/transactions from SimpleFIN.

        Extracts transactions from the cached /accounts response.

        Args:
            account_id: If provided, fetch activities only for this account.
                       If None, fetch activities for all accounts.

        Returns:
            List of ProviderActivity objects.
        """
        data = self._fetch_data()
        accounts_data = data.get("accounts", [])

        activities = []
        for sf_account in accounts_data:
            acct_id = sf_account.get("id", "")

            if account_id and acct_id != account_id:
                continue

            transactions = sf_account.get("transactions") or []
            for txn in transactions:
                activity = self._map_simplefin_transaction(txn, acct_id)
                if activity:
                    activities.append(activity)

        return activities

    def _map_simplefin_transaction(
        self, txn: dict, account_id: str
    ) -> ProviderActivity | None:
        """Map a SimpleFIN transaction to ProviderActivity.

        Args:
            txn: SimpleFIN transaction dict.
            account_id: The account ID this transaction belongs to.

        Returns:
            ProviderActivity or None if the transaction can't be mapped.
        """
        external_id = txn.get("id")
        if not external_id:
            return None

        # Parse date from Unix timestamp
        activity_date = parse_unix_timestamp(txn.get("posted"))
        if not activity_date:
            # Fall back to transacted_at
            activity_date = parse_unix_timestamp(txn.get("transacted_at"))
        if not activity_date:
            return None

        # Build description from available fields
        parts = []
        payee = txn.get("payee")
        if payee:
            parts.append(payee)
        desc = txn.get("description")
        if desc:
            parts.append(desc)
        memo = txn.get("memo")
        if memo:
            parts.append(memo)
        description = " - ".join(parts) if parts else None

        # Parse amount
        amount_raw = txn.get("amount")
        amount = Decimal(str(amount_raw)) if amount_raw is not None else None

        # Infer activity type
        activity_type = self._infer_activity_type(txn, amount)

        return ProviderActivity(
            account_id=account_id,
            external_id=str(external_id),
            activity_date=activity_date,
            type=activity_type,
            description=description,
            amount=amount,
            currency=txn.get("currency"),
            raw_data=txn,
        )

    def _infer_activity_type(self, txn: dict, amount: Decimal | None) -> str:
        """Infer activity type from SimpleFIN transaction data.

        Uses keyword matching on description/payee, then falls back to
        amount sign.

        Args:
            txn: SimpleFIN transaction dict.
            amount: Parsed amount (may be None).

        Returns:
            Activity type string.
        """
        # Build searchable text
        text = " ".join(
            str(v).lower()
            for v in [txn.get("payee"), txn.get("description"), txn.get("memo")]
            if v
        )

        # Keyword matching
        if any(kw in text for kw in ["dividend", "dist", "distribution"]):
            return "dividend"
        if any(kw in text for kw in ["interest"]):
            return "interest"
        if any(kw in text for kw in ["buy", "purchase", "bought"]):
            return "buy"
        if any(kw in text for kw in ["sell", "sold", "sale"]):
            return "sell"
        if any(kw in text for kw in ["transfer", "xfer"]):
            return "transfer"
        if any(kw in text for kw in ["fee", "commission"]):
            return "fee"
        if any(kw in text for kw in ["deposit"]):
            return "deposit"
        if any(kw in text for kw in ["withdrawal", "withdraw"]):
            return "withdrawal"

        # Fall back to amount sign
        if amount is not None:
            if amount > 0:
                return "deposit"
            elif amount < 0:
                return "withdrawal"

        return "other"

    @staticmethod
    def _parse_simplefin_errors(raw_errors: list) -> list[ProviderSyncError]:
        """Parse SimpleFIN error strings into structured ProviderSyncError objects.

        Recognizes patterns like "Connection to {institution} may need attention"
        and populates institution_name for direct matching against accounts.

        Args:
            raw_errors: Raw error values from the SimpleFIN API response.

        Returns:
            List of ProviderSyncError objects.
        """
        import re

        pattern = re.compile(
            r"connection to (.+?) may need attention", re.IGNORECASE
        )
        result: list[ProviderSyncError] = []
        for raw in raw_errors:
            msg = str(raw)
            match = pattern.search(msg)
            if match:
                result.append(ProviderSyncError(
                    message=msg,
                    category=ErrorCategory.CONNECTION,
                    institution_name=match.group(1).strip(),
                    retriable=True,
                ))
            else:
                result.append(ProviderSyncError(
                    message=msg,
                    category=ErrorCategory.UNKNOWN,
                ))
        return result

    def sync_all(self) -> ProviderSyncResult:
        """Fetch all holdings, accounts, activities, errors, and balance dates from SimpleFIN.

        Uses a single _fetch_data() call (cached) for both account and holdings
        data, avoiding redundant API calls against SimpleFIN's rate limit.

        Returns:
            ProviderSyncResult with holdings, accounts, activities,
            provider-reported errors, and per-account balance dates.
        """
        data = self._fetch_data()

        # Extract and parse provider-level errors
        raw_errors = data.get("errors", [])
        errors = self._parse_simplefin_errors(raw_errors)
        if errors:
            logger.warning("SimpleFIN: provider reported errors: %s", [str(e) for e in errors])

        # Build account list and balance dates from the same response
        accounts: list[ProviderAccount] = []
        balance_dates: dict[str, datetime | None] = {}
        for sf_account in data.get("accounts", []):
            acct_id = sf_account.get("id", "")

            # Build ProviderAccount
            institution = "Unknown"
            org = sf_account.get("org")
            if org:
                institution = org.get("name", "Unknown")
            accounts.append(
                ProviderAccount(
                    id=acct_id,
                    name=sf_account.get("name") or "Unnamed Account",
                    institution=institution,
                    account_number=None,
                )
            )

            # Extract balance date (Unix timestamp -> UTC datetime)
            balance_dates[acct_id] = parse_unix_timestamp(
                sf_account.get("balance-date")
            )

        # Reuse existing get_holdings() for the holdings data
        holdings = self.get_holdings()

        # Fetch activities (best-effort — don't fail the sync)
        activities: list[ProviderActivity] = []
        try:
            activities = self.get_activities()
        except Exception:
            logger.debug("SimpleFIN: activity fetch failed", exc_info=True)

        logger.info(
            "SimpleFIN: %d accounts, %d holdings, %d activities",
            len(accounts), len(holdings), len(activities),
        )

        return ProviderSyncResult(
            holdings=holdings,
            accounts=accounts,
            errors=errors,
            balance_dates=balance_dates,
            activities=activities,
        )

    def clear_cache(self) -> None:
        """Clear the cached data.

        Call this to force a fresh fetch on the next request.
        """
        self._cache = None
        self._cache_time = None
