"""Interactive Brokers Flex Web Service client.

This module implements the ProviderClient protocol for IBKR integration
via the Flex Web Service, using the ibflex library to download and parse
Flex Query reports containing positions, cash balances, and trades.
"""

import dataclasses
import logging
from datetime import datetime
from decimal import Decimal

from ibflex import client, enums, parser
from ibflex.Types import FlexQueryResponse

from config import settings
from integrations.parsing_utils import date_to_datetime, ensure_utc
from integrations.provider_protocol import (
    ErrorCategory,
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncError,
    ProviderSyncResult,
)


logger = logging.getLogger(__name__)


class IBKRFlexClient:
    """Wrapper around the IBKR Flex Web Service API.

    Implements the ProviderClient protocol for multi-provider support.
    Uses ibflex library to download and parse Flex Query XML reports.

    The Flex Web Service has strict rate limits, so the parsed response
    is cached after the first download. Call clear_cache() to force a
    fresh download on the next request.
    """

    def __init__(
        self,
        token: str | None = None,
        query_id: str | None = None,
    ):
        """Initialize the client with credentials.

        Args:
            token: Flex Web Service token (defaults to settings).
            query_id: Flex Query ID (defaults to settings).
        """
        self._token = token or settings.IBKR_FLEX_TOKEN
        self._query_id = query_id or settings.IBKR_FLEX_QUERY_ID
        self._cached_response: FlexQueryResponse | None = None

    @property
    def provider_name(self) -> str:
        """Return the provider name for database storage."""
        return "IBKR"

    def is_configured(self) -> bool:
        """Check if IBKR Flex credentials are configured.

        Returns:
            True if both token and query ID are present, False otherwise.
        """
        return bool(self._token) and bool(self._query_id)

    def _fetch_statement(self) -> FlexQueryResponse:
        """Download and parse a Flex Query report.

        Returns the cached response if available. The Flex Web Service
        has strict rate limits, so we avoid redundant downloads.

        Returns:
            Parsed FlexQueryResponse containing all statement data.

        Raises:
            ibflex.client.IbflexClientError: If download fails.
        """
        if self._cached_response is not None:
            return self._cached_response

        data = client.download(self._token, self._query_id)
        self._cached_response = parser.parse(data)
        return self._cached_response

    def clear_cache(self) -> None:
        """Clear the cached response.

        Call this to force a fresh download on the next request.
        """
        self._cached_response = None

    def get_accounts(self) -> list[ProviderAccount]:
        """Fetch all accounts from the Flex report.

        Returns:
            List of ProviderAccount objects, one per unique accountId.
        """
        response = self._fetch_statement()
        return self._extract_accounts(response)

    def _extract_accounts(self, response: FlexQueryResponse) -> list[ProviderAccount]:
        """Extract accounts from a parsed Flex response."""
        accounts = []
        for stmt in response.FlexStatements:
            name = self._get_account_name(stmt)
            accounts.append(
                ProviderAccount(
                    id=stmt.accountId,
                    name=name,
                    institution="Interactive Brokers",
                    account_number=None,
                )
            )
        return accounts

    @staticmethod
    def _get_account_name(stmt) -> str:
        """Derive a display name for an account without exposing the account ID.

        Preference order:
        1. acctAlias (user-set nickname in IBKR)
        2. "Interactive Brokers {accountType} Account" (e.g. "Individual")
        3. "Interactive Brokers Account" (generic fallback)
        """
        info = stmt.AccountInformation
        if info:
            if info.acctAlias:
                return info.acctAlias
            if info.accountType:
                return f"Interactive Brokers {info.accountType} Account"
        return "Interactive Brokers Account"

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Fetch holdings from the Flex report.

        Args:
            account_id: If provided, fetch holdings only for this account.
                       If None, fetch holdings for all accounts.

        Returns:
            List of ProviderHolding objects.
        """
        response = self._fetch_statement()
        return self._extract_holdings(response, account_id)

    def _extract_holdings(
        self, response: FlexQueryResponse, account_id: str | None = None
    ) -> list[ProviderHolding]:
        """Extract holdings from a parsed Flex response."""
        holdings = []
        for stmt in response.FlexStatements:
            if account_id and stmt.accountId != account_id:
                continue

            # Map OpenPositions to holdings
            for pos in stmt.OpenPositions:
                holding = self._map_position(pos)
                if holding:
                    holdings.append(holding)

            # Map CashReportCurrency to cash holdings
            for cash in stmt.CashReport:
                holding = self._map_cash(cash)
                if holding:
                    holdings.append(holding)

        return holdings

    def _map_position(self, pos) -> ProviderHolding | None:
        """Map an OpenPosition to a ProviderHolding.

        Args:
            pos: ibflex OpenPosition dataclass.

        Returns:
            ProviderHolding or None if the position can't be mapped.
        """
        if pos.symbol is None:
            return None

        quantity = pos.position if pos.position is not None else Decimal("0")
        price = pos.markPrice if pos.markPrice is not None else Decimal("0")

        if pos.positionValue is not None:
            market_value = pos.positionValue
        else:
            market_value = quantity * price

        # Extract per-unit cost basis
        cost_basis = getattr(pos, "costBasisPrice", None)
        if cost_basis is not None and cost_basis <= 0:
            cost_basis = None

        # Build raw_data from dataclass fields
        try:
            raw_data = dataclasses.asdict(pos)
            raw_data = {
                k: str(v) if v is not None else None for k, v in raw_data.items()
            }
        except Exception:
            raw_data = None

        return ProviderHolding(
            account_id=pos.accountId or "",
            symbol=pos.symbol,
            quantity=quantity,
            price=price,
            market_value=market_value,
            currency=pos.currency or "USD",
            name=pos.description,
            cost_basis=cost_basis,
            raw_data=raw_data,
        )

    def _map_cash(self, cash) -> ProviderHolding | None:
        """Map a CashReportCurrency to a synthetic cash ProviderHolding.

        Args:
            cash: ibflex CashReportCurrency dataclass.

        Returns:
            ProviderHolding or None if the cash entry should be skipped.
        """
        if cash.currency is None or cash.currency == "BASE_SUMMARY":
            return None

        if cash.endingCash is None or cash.endingCash == Decimal("0"):
            return None

        return ProviderHolding(
            account_id=cash.accountId or "",
            symbol=f"_CASH:{cash.currency}",
            quantity=cash.endingCash,
            price=Decimal("1"),
            market_value=cash.endingCash,
            currency=cash.currency,
            name=f"{cash.currency} Cash",
        )

    def get_activities(self) -> list[ProviderActivity]:
        """Fetch activities/trades from the Flex report.

        Returns:
            List of ProviderActivity objects.
        """
        response = self._fetch_statement()
        return self._extract_activities(response)

    def _extract_activities(
        self, response: FlexQueryResponse
    ) -> list[ProviderActivity]:
        """Extract activities from a parsed Flex response."""
        activities = []
        for stmt in response.FlexStatements:
            for trade in stmt.Trades:
                activity = self._map_trade(trade)
                if activity:
                    activities.append(activity)
            for cash_tx in stmt.CashTransactions:
                activity = self._map_cash_transaction(cash_tx)
                if activity:
                    activities.append(activity)
        return activities

    def _map_trade(self, trade) -> ProviderActivity | None:
        """Map a Trade to a ProviderActivity.

        Args:
            trade: ibflex Trade dataclass.

        Returns:
            ProviderActivity or None if the trade can't be mapped.
        """
        # Determine external_id
        external_id = trade.tradeID or trade.transactionID
        if not external_id:
            return None

        # Determine activity date
        activity_date = self._get_trade_datetime(trade)
        if not activity_date:
            return None

        # Map buySell to activity type
        activity_type = self._map_buy_sell(trade.buySell)

        # Determine settlement date
        settlement_date = None
        if trade.settleDateTarget is not None:
            settlement_date = date_to_datetime(trade.settleDateTarget)

        # Build raw_data from dataclass fields
        try:
            raw_data = dataclasses.asdict(trade)
            # Convert non-serializable types to strings
            raw_data = {
                k: str(v) if v is not None else None for k, v in raw_data.items()
            }
        except Exception:
            raw_data = None

        return ProviderActivity(
            account_id=trade.accountId or "",
            external_id=str(external_id),
            activity_date=activity_date,
            type=activity_type,
            amount=trade.netCash if trade.netCash is not None else trade.proceeds,
            description=trade.description,
            settlement_date=settlement_date,
            ticker=trade.symbol,
            units=trade.quantity,
            price=trade.tradePrice,
            currency=trade.currency,
            fee=trade.ibCommission,
            raw_data=raw_data,
        )

    def _get_trade_datetime(self, trade) -> datetime | None:
        """Extract a timezone-aware datetime from a Trade.

        Tries trade.dateTime first, then combines tradeDate + tradeTime.
        """
        if trade.dateTime is not None:
            return ensure_utc(trade.dateTime)

        if trade.tradeDate is not None:
            dt = date_to_datetime(trade.tradeDate)
            if trade.tradeTime is not None:
                dt = dt.replace(
                    hour=trade.tradeTime.hour,
                    minute=trade.tradeTime.minute,
                    second=trade.tradeTime.second,
                )
            return dt

        return None

    def _map_buy_sell(self, buy_sell) -> str:
        """Map ibflex BuySell enum to activity type string."""
        if buy_sell in (enums.BuySell.BUY, enums.BuySell.CANCELBUY):
            return "buy"
        if buy_sell in (enums.BuySell.SELL, enums.BuySell.CANCELSELL):
            return "sell"
        return "other"

    def _map_cash_action(self, cash_action, amount) -> str:
        """Map ibflex CashAction to activity type string.

        Handles both CashAction enum values and raw strings, since ibflex
        may return either depending on the XML content.

        Args:
            cash_action: CashAction enum or raw string from the XML.
            amount: Transaction amount, used to distinguish deposits from withdrawals.

        Returns:
            Activity type string.
        """
        if isinstance(cash_action, enums.CashAction):
            label = cash_action.value.lower()
        elif isinstance(cash_action, str):
            label = cash_action.lower()
        else:
            return "other"

        if "dividend" in label or "payment in lieu" in label:
            return "dividend"
        if "deposit" in label or "withdrawal" in label:
            if amount is not None and amount < 0:
                return "withdrawal"
            return "deposit"
        if "interest" in label:
            return "interest"
        if "withholding tax" in label:
            return "tax"
        if "fee" in label or "commission" in label:
            return "fee"
        return "other"

    def _map_cash_transaction(self, cash_tx) -> ProviderActivity | None:
        """Map a CashTransaction to a ProviderActivity.

        Args:
            cash_tx: ibflex CashTransaction dataclass.

        Returns:
            ProviderActivity or None if the transaction can't be mapped.
        """
        # Skip entries without accountId — IBKR emits duplicate pairs
        # (one with accountId, one without) and we only want the real one.
        if not cash_tx.accountId:
            return None

        # Require transactionID for deduplication
        if not cash_tx.transactionID:
            return None

        # Determine activity date
        activity_date = None
        if cash_tx.dateTime is not None:
            activity_date = ensure_utc(cash_tx.dateTime)
        elif cash_tx.reportDate is not None:
            activity_date = date_to_datetime(cash_tx.reportDate)
        if not activity_date:
            return None

        # Map cash action type
        activity_type = self._map_cash_action(cash_tx.type, cash_tx.amount)

        # Settlement date
        settlement_date = None
        if cash_tx.settleDate is not None:
            settlement_date = date_to_datetime(cash_tx.settleDate)

        account_id = cash_tx.accountId

        # Build raw_data from dataclass fields
        try:
            raw_data = dataclasses.asdict(cash_tx)
            raw_data = {
                k: str(v) if v is not None else None for k, v in raw_data.items()
            }
        except Exception:
            raw_data = None

        return ProviderActivity(
            account_id=account_id,
            external_id=f"CT:{cash_tx.transactionID}",
            activity_date=activity_date,
            type=activity_type,
            amount=cash_tx.amount,
            description=cash_tx.description,
            settlement_date=settlement_date,
            ticker=cash_tx.symbol,
            units=None,
            price=None,
            currency=cash_tx.currency,
            fee=None,
            raw_data=raw_data,
        )

    def sync_all(self) -> ProviderSyncResult:
        """Fetch all data from a single Flex report download.

        Returns:
            ProviderSyncResult with holdings, accounts, activities,
            errors, and per-account balance dates.
        """
        try:
            response = self._fetch_statement()
        except Exception as e:
            return ProviderSyncResult(
                holdings=[],
                accounts=[],
                errors=[ProviderSyncError(
                    message=str(e),
                    category=ErrorCategory.CONNECTION,
                    retriable=True,
                )],
                balance_dates={},
                activities=[],
            )

        accounts = self._extract_accounts(response)
        holdings = self._extract_holdings(response)

        # Build balance dates from statement metadata
        balance_dates: dict[str, datetime | None] = {}
        for stmt in response.FlexStatements:
            if stmt.whenGenerated is not None:
                balance_dates[stmt.accountId] = ensure_utc(stmt.whenGenerated)
            elif stmt.toDate is not None:
                balance_dates[stmt.accountId] = date_to_datetime(stmt.toDate)
            else:
                balance_dates[stmt.accountId] = None

        # Activities are best-effort
        activities: list[ProviderActivity] = []
        try:
            activities = self._extract_activities(response)
        except Exception:
            logger.exception("Failed to extract activities from IBKR Flex report")

        logger.info(
            "IBKR: %d accounts, %d holdings, %d activities fetched",
            len(accounts), len(holdings), len(activities),
        )

        return ProviderSyncResult(
            holdings=holdings,
            accounts=accounts,
            errors=[],
            balance_dates=balance_dates,
            activities=activities,
        )
