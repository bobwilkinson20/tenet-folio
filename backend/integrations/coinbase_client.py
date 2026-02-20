"""Coinbase Advanced Trade API client.

This module implements the ProviderClient protocol for Coinbase integration
via the coinbase-advanced-py SDK, fetching portfolios, currency balances,
and trade fills.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from coinbase.rest import RESTClient

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

# Fiat currencies and stablecoins treated as cash (price=1, symbol=_CASH:{code})
FIAT_CURRENCIES = frozenset({
    "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "CNY", "HKD", "SGD",
    "NZD", "KRW", "INR", "BRL", "MXN", "SEK", "NOK", "DKK", "PLN", "CZK",
    "HUF", "TRY", "ZAR", "ARS", "CLP", "COP", "PEN", "TWD", "THB", "PHP",
    "IDR", "MYR", "VND",
    # Stablecoins treated as cash
    "USDC", "USDT",
})

# Mapping from Coinbase v2 transaction types to ProviderActivity types
V2_TYPE_MAP = {
    "send": "transfer",
    "receive": "receive",
    "fiat_deposit": "deposit",
    "fiat_withdrawal": "withdrawal",
    "staking_transfer": "other",
    "unstaking_transfer": "other",
    "earn_payout": "dividend",
    "staking_reward": "dividend",
    "inflation_reward": "dividend",
    "transfer": "transfer",
    "buy": "buy",
    "sell": "sell",
}

# Human-readable description templates for v2 transaction types.
# Used as fallback when details.title is not available from the API.
# The placeholder {amount} is replaced with "<quantity> <ticker>".
V2_DESCRIPTION_MAP = {
    "send": "Sent {amount}",
    "receive": "Received {amount}",
    "staking_transfer": "Staked {amount}",
    "unstaking_transfer": "Unstaked {amount}",
    "staking_reward": "Staking reward: {amount}",
    "inflation_reward": "Staking reward: {amount}",
    "earn_payout": "Earn payout: {amount}",
}

# V2 transaction types to skip (duplicated by Advanced Trade fills)
V2_SKIP_TYPES = frozenset({"advanced_trade_fill"})


class CoinbaseClient:
    """Wrapper around the Coinbase Advanced Trade API.

    Implements the ProviderClient protocol for multi-provider support.
    Uses the coinbase-advanced-py SDK to fetch portfolio, balance, and
    trade data.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        key_file: str | None = None,
    ):
        """Initialize the client with credentials.

        Args:
            api_key: CDP API key (defaults to settings).
            api_secret: CDP API secret / PEM key (defaults to settings).
            key_file: Path to CDP API key JSON file (defaults to settings).
        """
        self._api_key = api_key or settings.COINBASE_API_KEY
        self._api_secret = api_secret or settings.COINBASE_API_SECRET
        self._key_file = key_file or settings.COINBASE_KEY_FILE

        # If a key file is provided and inline creds are not, read from file
        if self._key_file and not (self._api_key and self._api_secret):
            self._load_key_file(self._key_file)

        # Lazily created on first use
        self._client: RESTClient | None = None

    def _load_key_file(self, path_str: str) -> None:
        """Read API key and secret from a CDP JSON key file.

        Accepts both ``"name"`` and ``"id"`` as the key field, since
        Coinbase has shipped key files with both field names.
        """
        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            logger.warning("Coinbase key file not found: %s", path)
            return

        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read Coinbase key file: %s", e)
            return

        self._api_key = data.get("name") or data.get("id") or ""
        self._api_secret = data.get("privateKey") or ""

    def _get_client(self) -> RESTClient:
        """Return (and cache) a RESTClient instance."""
        if self._client is None:
            self._client = RESTClient(
                api_key=self._api_key,
                api_secret=self._api_secret,
            )
        return self._client

    @property
    def provider_name(self) -> str:
        """Return the provider name for database storage."""
        return "Coinbase"

    def is_configured(self) -> bool:
        """Check if Coinbase credentials are configured.

        Returns:
            True if both API key and secret are present, False otherwise.
        """
        return bool(self._api_key) and bool(self._api_secret)

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def get_accounts(self) -> list[ProviderAccount]:
        """Fetch all portfolios from Coinbase.

        Each Coinbase portfolio maps to one ProviderAccount.

        Returns:
            List of ProviderAccount objects.
        """
        client = self._get_client()
        response = client.get_portfolios()

        portfolios = self._extract_list(response, "portfolios")

        accounts = []
        for portfolio in portfolios:
            pid = self._get_field(portfolio, "uuid") or self._get_field(portfolio, "id") or ""
            name = self._get_field(portfolio, "name") or "Coinbase Portfolio"
            accounts.append(
                ProviderAccount(
                    id=pid,
                    name=name,
                    institution="Coinbase",
                )
            )
        return accounts

    # ------------------------------------------------------------------
    # Holdings
    # ------------------------------------------------------------------

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Fetch holdings for one or all portfolios.

        Args:
            account_id: Portfolio UUID. If None, fetch for all portfolios.

        Returns:
            List of ProviderHolding objects.
        """
        if account_id:
            return self._get_holdings_for_portfolio(account_id)

        accounts = self.get_accounts()
        holdings: list[ProviderHolding] = []
        for account in accounts:
            holdings.extend(self._get_holdings_for_portfolio(account.id))
        return holdings

    def _get_holdings_for_portfolio(
        self, portfolio_id: str
    ) -> list[ProviderHolding]:
        """Fetch all non-zero positions for a single portfolio.

        Uses get_portfolio_breakdown() which returns spot_positions with
        total balances (staked + liquid) and fiat valuations.
        """
        client = self._get_client()
        response = client.get_portfolio_breakdown(portfolio_id)

        breakdown = self._get_field(response, "breakdown")
        positions = self._extract_list(breakdown, "spot_positions")

        holdings: list[ProviderHolding] = []
        for pos in positions:
            holding = self._map_spot_position(pos, portfolio_id)
            if holding is not None:
                holdings.append(holding)
        return holdings

    def _map_spot_position(
        self, pos, portfolio_id: str
    ) -> ProviderHolding | None:
        """Map a spot position from portfolio breakdown to a ProviderHolding.

        Skips zero-quantity positions.
        """
        asset = self._get_field(pos, "asset") or "UNKNOWN"
        symbol = asset.upper()

        quantity = self._to_decimal(self._get_field(pos, "total_balance_crypto")) or Decimal("0")
        market_value = self._to_decimal(self._get_field(pos, "total_balance_fiat")) or Decimal("0")

        if quantity == Decimal("0"):
            return None

        if symbol in FIAT_CURRENCIES:
            return ProviderHolding(
                account_id=portfolio_id,
                symbol=f"_CASH:{symbol}",
                quantity=quantity,
                price=Decimal("1"),
                market_value=quantity,
                currency=symbol,
                name=f"{symbol} Cash",
            )

        # Derive price from fiat / crypto
        price = (market_value / quantity) if quantity else Decimal("0")

        # Extract per-unit cost basis
        unit_cost: Decimal | None = None
        avg_entry = self._get_field(
            self._get_field(pos, "average_entry_price"), "value"
        )
        if avg_entry is not None:
            unit_cost = self._to_decimal(avg_entry)
            if unit_cost is not None and unit_cost <= 0:
                unit_cost = None
        if unit_cost is None:
            # Fall back to total cost_basis / quantity
            total_cost = self._get_field(
                self._get_field(pos, "cost_basis"), "value"
            )
            if total_cost is not None and quantity and quantity > 0:
                total_dec = self._to_decimal(total_cost)
                if total_dec is not None and total_dec > 0:
                    unit_cost = total_dec / quantity

        return ProviderHolding(
            account_id=portfolio_id,
            symbol=symbol,
            quantity=quantity,
            price=price,
            market_value=market_value,
            currency="USD",
            name=asset,
            cost_basis=unit_cost,
            raw_data=self._to_raw_dict(pos),
        )

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------

    def get_activities(
        self, account_id: str | None = None, days: int = 90
    ) -> list[ProviderActivity]:
        """Fetch trade fills and v2 transactions from Coinbase.

        Combines Advanced Trade fills with v2 transactions (deposits,
        withdrawals, staking rewards, etc.).  V2 transactions are only
        fetched when ``account_id`` is provided because they require
        iterating per-currency accounts within a portfolio.

        Args:
            account_id: Portfolio UUID to filter by (optional).
            days: Number of days of history to fetch (default 90).

        Returns:
            List of ProviderActivity objects.
        """
        fills = self._get_all_fills(account_id, days=days)

        activities: list[ProviderActivity] = []
        for fill in fills:
            activity = self._map_fill(fill, account_id)
            if activity is not None:
                activities.append(activity)

        # V2 transactions (deposits, withdrawals, staking, etc.)
        if account_id:
            try:
                v2_activities = self._get_all_v2_transactions(
                    account_id, days=days
                )
                activities.extend(v2_activities)
            except Exception:
                logger.warning(
                    "Failed to fetch v2 transactions for portfolio %s",
                    account_id,
                    exc_info=True,
                )

        return activities

    def _get_all_fills(
        self, portfolio_id: str | None = None, days: int = 90
    ) -> list:
        """Paginate through client.get_fills().

        Args:
            portfolio_id: Portfolio UUID to filter by (optional).
            days: Number of days of history to fetch (default 90).
        """
        client = self._get_client()
        all_fills: list = []
        cursor: str | None = None

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        start_ts = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        while True:
            kwargs: dict = {
                "limit": 100,
                "start_sequence_timestamp": start_ts,
            }
            if portfolio_id:
                kwargs["retail_portfolio_id"] = portfolio_id
            if cursor:
                kwargs["cursor"] = cursor

            response = client.get_fills(**kwargs)

            fills = self._extract_list(response, "fills")
            all_fills.extend(fills)

            next_cursor = self._get_field(response, "cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        return all_fills

    # ------------------------------------------------------------------
    # V2 Transactions (deposits, withdrawals, staking, etc.)
    # ------------------------------------------------------------------

    def _get_currency_accounts(self, portfolio_id: str) -> list:
        """Paginate through v2 accounts (currency wallets) for a portfolio.

        Args:
            portfolio_id: The retail portfolio UUID to filter by.

        Returns:
            List of raw v2 account dicts.
        """
        client = self._get_client()
        all_accounts: list = []
        cursor: str | None = None

        while True:
            kwargs: dict = {"limit": 100}
            if portfolio_id:
                kwargs["retail_portfolio_id"] = portfolio_id
            if cursor:
                kwargs["starting_after"] = cursor

            response = client.get_accounts(**kwargs)

            accounts = self._extract_list(response, "accounts")
            if not accounts:
                break
            all_accounts.extend(accounts)

            cursor_obj = self._get_field(response, "pagination") or {}
            next_cursor = self._get_field(cursor_obj, "next_starting_after")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        return all_accounts

    def _get_v2_transactions(self, currency_account_uuid: str) -> list:
        """Paginate through v2 transactions for a single currency account.

        Uses the REST client's generic ``get()`` method since the SDK does
        not expose a typed helper for this endpoint.

        Args:
            currency_account_uuid: The v2 currency-account UUID.

        Returns:
            List of raw v2 transaction dicts.
        """
        client = self._get_client()
        all_txns: list = []
        cursor: str | None = None

        while True:
            kwargs: dict = {"limit": 100}
            if cursor:
                kwargs["starting_after"] = cursor

            response = client.get(
                f"/v2/accounts/{currency_account_uuid}/transactions",
                params=kwargs,
            )

            # Response may be a dict or an object; normalise
            if isinstance(response, dict):
                data = response.get("data", []) or []
            else:
                data = getattr(response, "data", None) or []

            if not data:
                break
            all_txns.extend(data)

            # Pagination: look for pagination.next_starting_after
            if isinstance(response, dict):
                pagination = response.get("pagination", {}) or {}
            else:
                pagination = getattr(response, "pagination", None) or {}
            next_cursor = (
                pagination.get("next_starting_after")
                if isinstance(pagination, dict)
                else getattr(pagination, "next_starting_after", None)
            )
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        return all_txns

    def _map_v2_transaction(
        self, txn, portfolio_id: str
    ) -> ProviderActivity | None:
        """Map a v2 transaction to a ProviderActivity.

        Skips advanced_trade_fill (duplicated by fills), non-completed
        transactions, and transactions missing required fields.

        Args:
            txn: Raw v2 transaction dict/object.
            portfolio_id: The portfolio UUID to assign as account_id.

        Returns:
            A ProviderActivity or None if the transaction should be skipped.
        """
        txn_type = str(self._get_field(txn, "type") or "").lower()

        # Skip types that duplicate Advanced Trade data
        if txn_type in V2_SKIP_TYPES:
            return None

        # Only include completed transactions
        status = str(self._get_field(txn, "status") or "").lower()
        if status != "completed":
            return None

        # Required fields
        txn_id = self._get_field(txn, "id")
        if not txn_id:
            return None

        created_at = self._get_field(txn, "created_at")
        activity_date = parse_iso_datetime(created_at)
        if activity_date is None:
            return None

        # Amount (crypto)
        amount_obj = self._get_field(txn, "amount") or {}
        crypto_currency = str(
            self._get_field(amount_obj, "currency") or "UNKNOWN"
        ).upper()
        crypto_amount = self._to_decimal(self._get_field(amount_obj, "amount"))

        # Native amount (fiat value)
        native_obj = self._get_field(txn, "native_amount") or {}
        native_amount = self._to_decimal(self._get_field(native_obj, "amount"))

        # Normalize 'send' type: Coinbase uses 'send' for both directions.
        # Positive crypto amount means crypto was sent TO this wallet (= receive).
        if txn_type == "send" and crypto_amount is not None and crypto_amount >= 0:
            txn_type = "receive"

        # Determine activity type
        if txn_type == "trade":
            # Positive crypto amount = buy, negative = sell
            if crypto_amount is not None and crypto_amount < 0:
                activity_type = "sell"
            else:
                activity_type = "buy"
        else:
            activity_type = V2_TYPE_MAP.get(txn_type, "other")

        # Units = absolute value of crypto amount
        units = abs(crypto_amount) if crypto_amount is not None else None

        # Price = |native| / |crypto| when both are nonzero
        price: Decimal | None = None
        if (
            crypto_amount is not None
            and native_amount is not None
            and crypto_amount != 0
        ):
            price = abs(native_amount) / abs(crypto_amount)

        # Fee from network.transaction_fee.amount if present
        fee: Decimal | None = None
        network = self._get_field(txn, "network") or {}
        fee_obj = self._get_field(network, "transaction_fee") or {}
        fee_raw = self._get_field(fee_obj, "amount")
        if fee_raw is not None:
            fee = self._to_decimal(fee_raw)

        # Description
        description = self._get_field(txn, "details")
        if isinstance(description, dict):
            description = description.get("title") or description.get("subtitle")
        if not description:
            tmpl = V2_DESCRIPTION_MAP.get(txn_type)
            if tmpl and units is not None:
                description = tmpl.format(amount=f"{units} {crypto_currency}")
            else:
                description = f"{activity_type.upper()} {crypto_currency} on Coinbase"

        # Amount is always absolute for v2 transactions.  The activity
        # ``type`` (deposit, withdrawal, transfer, …) already conveys
        # the direction; using abs() avoids double-encoding the sign.
        # This differs from fills, where buys are negative (cash out)
        # and sells are positive (cash in), because fill amounts
        # represent net cash flow rather than a typed transaction.
        return ProviderActivity(
            account_id=portfolio_id,
            external_id=f"v2:{txn_id}",
            activity_date=activity_date,
            type=activity_type,
            amount=abs(native_amount) if native_amount is not None else None,
            description=str(description),
            ticker=crypto_currency if crypto_currency != "UNKNOWN" else None,
            units=units,
            price=price,
            currency=str(
                self._get_field(native_obj, "currency") or "USD"
            ).upper(),
            fee=fee,
            raw_data=self._to_raw_dict(txn),
        )

    def _get_all_v2_transactions(
        self, portfolio_id: str, days: int = 90
    ) -> list[ProviderActivity]:
        """Fetch and map all v2 transactions for a portfolio.

        Gets all currency accounts for the portfolio, then fetches v2
        transactions from each one. Errors on individual currency accounts
        are logged but do not block other accounts.

        Args:
            portfolio_id: The portfolio UUID.
            days: Number of days of history to include (default 90).

        Returns:
            List of mapped ProviderActivity objects.
        """
        try:
            currency_accounts = self._get_currency_accounts(portfolio_id)
        except Exception:
            logger.warning(
                "Failed to fetch v2 currency accounts for portfolio %s",
                portfolio_id,
                exc_info=True,
            )
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        activities: list[ProviderActivity] = []
        for ca in currency_accounts:
            ca_uuid = self._get_field(ca, "uuid") or self._get_field(ca, "id") or ""
            if not ca_uuid:
                continue
            try:
                txns = self._get_v2_transactions(ca_uuid)
            except Exception:
                logger.warning(
                    "Failed to fetch v2 transactions for currency account %s",
                    ca_uuid,
                    exc_info=True,
                )
                continue

            for txn in txns:
                activity = self._map_v2_transaction(txn, portfolio_id)
                if activity is not None and activity.activity_date >= cutoff:
                    activities.append(activity)

        return activities

    def _map_fill(self, fill, portfolio_id: str | None) -> ProviderActivity | None:
        """Map a Coinbase fill to a ProviderActivity."""
        # External ID
        external_id = (
            self._get_field(fill, "entry_id")
            or self._get_field(fill, "trade_id")
            or ""
        )
        if not external_id:
            return None

        # Product parsing: "BTC-USD" → ticker="BTC", currency="USD"
        product_id = self._get_field(fill, "product_id") or ""
        parts = product_id.split("-", 1)
        ticker = parts[0] if parts else None
        currency = parts[1] if len(parts) > 1 else "USD"

        # Side
        side = str(self._get_field(fill, "side") or "").upper()
        activity_type = "buy" if side == "BUY" else "sell" if side == "SELL" else "other"

        # Numeric fields
        price = self._to_decimal(self._get_field(fill, "price"))
        size = self._to_decimal(self._get_field(fill, "size"))
        commission = self._to_decimal(self._get_field(fill, "commission"))

        # Amount = price * size; negative for buys
        amount: Decimal | None = None
        if price is not None and size is not None:
            amount = price * size
            if activity_type == "buy":
                amount = -amount

        # Trade time
        trade_time = parse_iso_datetime(self._get_field(fill, "trade_time"))

        if trade_time is None:
            return None

        # Raw data for debugging
        raw_data = self._to_raw_dict(fill)

        # Determine account_id for this fill
        fill_account_id = portfolio_id or ""

        return ProviderActivity(
            account_id=fill_account_id,
            external_id=str(external_id),
            activity_date=trade_time,
            type=activity_type,
            amount=amount,
            description=f"{activity_type.upper()} {ticker or ''} on Coinbase",
            ticker=ticker,
            units=size,
            price=price,
            currency=currency,
            fee=commission,
            raw_data=raw_data,
        )

    # ------------------------------------------------------------------
    # sync_all
    # ------------------------------------------------------------------

    def sync_all(self) -> ProviderSyncResult:
        """Fetch all data from Coinbase.

        Returns:
            ProviderSyncResult with holdings, accounts, activities,
            errors, and per-account balance dates.
        """
        # Accounts
        try:
            accounts = self.get_accounts()
        except Exception as e:
            return ProviderSyncResult(
                holdings=[],
                accounts=[],
                errors=[ProviderSyncError(
                    message=f"Failed to fetch Coinbase accounts: {e}",
                    category=ErrorCategory.CONNECTION,
                    retriable=True,
                )],
                balance_dates={},
                activities=[],
            )

        # Holdings — per-portfolio, collect errors but continue
        all_holdings: list[ProviderHolding] = []
        errors: list[ProviderSyncError] = []
        balance_dates: dict[str, datetime | None] = {}
        now = datetime.now(timezone.utc)

        for account in accounts:
            try:
                holdings = self._get_holdings_for_portfolio(account.id)
                all_holdings.extend(holdings)
                balance_dates[account.id] = now
            except Exception as e:
                errors.append(ProviderSyncError(
                    message=f"Failed to fetch holdings for portfolio {account.name}: {e}",
                    category=ErrorCategory.DATA,
                    account_id=account.id,
                ))

        # Activities — per-portfolio so each fill gets the correct account_id
        activities: list[ProviderActivity] = []
        for account in accounts:
            try:
                activities.extend(self.get_activities(account_id=account.id))
            except Exception:
                logger.warning(
                    "Failed to fetch Coinbase activities for %s",
                    account.name,
                    exc_info=True,
                )

        logger.info(
            "Coinbase: %d accounts, %d holdings, %d activities fetched",
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
    # Helpers — defensive field extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _get_field(obj, field: str):
        """Extract a field from a dict or SDK object."""
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(field)
        return getattr(obj, field, None)

    @staticmethod
    def _extract_list(obj, field: str) -> list:
        """Extract a list field from a dict or SDK response object."""
        if obj is None:
            return []
        if isinstance(obj, dict):
            return obj.get(field, []) or []
        val = getattr(obj, field, None)
        return val if val is not None else []

    @classmethod
    def _get_nested_decimal(cls, obj, outer: str, inner: str) -> Decimal:
        """Extract a nested decimal value like obj.outer.inner."""
        outer_obj = cls._get_field(obj, outer)
        if outer_obj is None:
            return Decimal("0")
        raw = cls._get_field(outer_obj, inner)
        if raw is None:
            return Decimal("0")
        try:
            return Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @staticmethod
    def _to_decimal(value) -> Decimal | None:
        """Convert a value to Decimal, returning None on failure."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _to_raw_dict(obj) -> dict | None:
        """Convert an SDK response object to a plain dict for raw_data."""
        if obj is None:
            return None
        if isinstance(obj, dict):
            return {k: str(v) if v is not None else None for k, v in obj.items()}
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return {
                k: str(v) if v is not None else None
                for k, v in obj.__dict__.items()
                if not k.startswith("_")
            }
        return {"value": str(obj)}
