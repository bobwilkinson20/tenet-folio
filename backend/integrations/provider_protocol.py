"""Provider protocol definitions for multi-provider support.

This module defines the common interfaces that all data aggregation providers
(SnapTrade, SimpleFIN, etc.) must implement to work with the system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol


@dataclass
class ProviderAccount:
    """Normalized account data from any provider.

    All provider clients must map their account data to this format.
    """

    id: str  # Provider's external ID for the account
    name: str  # Account name/nickname
    institution: str  # Brokerage/bank name
    account_number: str | None = None  # Account number (if available)


@dataclass
class ProviderHolding:
    """Normalized holding data from any provider.

    All provider clients must map their holdings data to this format.
    """

    account_id: str  # Provider's account ID this holding belongs to
    symbol: str  # Ticker symbol
    quantity: Decimal  # Number of shares/units
    price: Decimal  # Current price per unit
    market_value: Decimal  # Total market value (quantity * price)
    currency: str  # Currency code (e.g., "USD")
    name: str | None = None  # Security name (if available)
    cost_basis: Decimal | None = None  # Per-unit cost basis (if available)
    raw_data: dict | None = None  # Raw provider response for debugging


@dataclass
class ProviderActivity:
    """Normalized activity/transaction data from any provider.

    All provider clients must map their activity data to this format.
    """

    account_id: str  # Provider's account ID this activity belongs to
    external_id: str  # Provider's unique ID for this activity
    activity_date: datetime  # Date the activity occurred
    type: str  # e.g., "buy", "sell", "dividend", "transfer", "deposit", "withdrawal"
    amount: Decimal | None = None  # Total amount (monetary value)
    description: str | None = None  # Human-readable description
    settlement_date: datetime | None = None  # Settlement date (if available)
    ticker: str | None = None  # Ticker symbol (if applicable)
    units: Decimal | None = None  # Number of shares/units (if applicable)
    price: Decimal | None = None  # Price per unit (if applicable)
    currency: str | None = None  # Currency code (e.g., "USD")
    fee: Decimal | None = None  # Fee/commission (if applicable)
    raw_data: dict | None = None  # Raw provider response for debugging


class ErrorCategory(str, Enum):
    """Category of a provider sync error."""

    CONNECTION = "connection"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    DATA = "data"
    UNKNOWN = "unknown"


@dataclass
class ProviderSyncError:
    """Structured error from a provider sync operation.

    Replaces plain error strings with typed, parseable error objects.
    """

    message: str
    category: ErrorCategory = ErrorCategory.UNKNOWN
    institution_name: str | None = None
    account_id: str | None = None
    retriable: bool = False

    def __str__(self) -> str:
        return self.message


@dataclass
class ProviderSyncResult:
    """Result of a provider sync_all() call.

    Wraps holdings and account data with any errors reported by the provider
    and per-account balance dates.
    """

    holdings: list[ProviderHolding]
    accounts: list[ProviderAccount] = field(default_factory=list)
    errors: list[ProviderSyncError] = field(default_factory=list)
    balance_dates: dict[str, datetime | None] = field(default_factory=dict)
    activities: list[ProviderActivity] = field(default_factory=list)


class ProviderClient(Protocol):
    """Protocol that all provider clients must implement.

    This defines the contract for data aggregation providers.
    Any new provider integration must implement these methods.
    """

    @property
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'SnapTrade', 'SimpleFIN').

        This name is stored in the database to identify which provider
        an account came from.
        """
        ...

    def is_configured(self) -> bool:
        """Check if this provider has valid credentials configured.

        Returns:
            True if the provider can be used (credentials are present),
            False otherwise.
        """
        ...

    def get_accounts(self) -> list[ProviderAccount]:
        """Fetch all accounts from this provider.

        Returns:
            List of normalized account data.

        Raises:
            ValueError: If credentials are not configured.
            Exception: If the provider API call fails.
        """
        ...

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Fetch holdings from this provider.

        Args:
            account_id: If provided, fetch holdings only for this account.
                       If None, fetch holdings for all accounts.

        Returns:
            List of normalized holding data.

        Raises:
            ValueError: If credentials are not configured.
            Exception: If the provider API call fails.
        """
        ...
