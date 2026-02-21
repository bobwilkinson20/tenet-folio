"""Mock implementations for external services."""

from datetime import date, datetime, timezone
from decimal import Decimal

from integrations.exceptions import ProviderAuthError, ProviderConnectionError
from integrations.market_data_protocol import PriceResult
from integrations.provider_protocol import (
    ErrorCategory,
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncError,
    ProviderSyncResult,
)
from integrations.provider_registry import ProviderRegistry
from integrations.simplefin_client import _generate_synthetic_symbol
from integrations.snaptrade_client import (
    SnapTradeAccount,
    SnapTradeClientProtocol,
    SnapTradeHolding,
)


class MockSnapTradeClient(SnapTradeClientProtocol):
    """Mock SnapTrade client for testing.

    Implements both the legacy SnapTradeClientProtocol and the new
    ProviderClient protocol for backward compatibility during migration.
    """

    def __init__(
        self,
        accounts: list[SnapTradeAccount] | None = None,
        holdings: list[SnapTradeHolding] | None = None,
        should_fail: bool = False,
        failure_message: str = "Mock SnapTrade error",
        failure_type: str = "generic",
        name: str = "SnapTrade",
        balance_dates: dict[str, datetime | None] | None = None,
        activities: list[ProviderActivity] | None = None,
    ):
        self._accounts = accounts or []
        self._holdings = holdings or []
        self._should_fail = should_fail
        self._failure_message = failure_message
        self._failure_type = failure_type
        self._name = name
        self._balance_dates = balance_dates or {}
        self._activities = activities or []

    def _raise_failure(self) -> None:
        """Raise the appropriate exception based on failure_type."""
        if self._failure_type == "auth":
            raise ProviderAuthError(self._failure_message, provider_name=self._name)
        elif self._failure_type == "connection":
            raise ProviderConnectionError(self._failure_message, provider_name=self._name)
        else:
            raise Exception(self._failure_message)

    # ProviderClient protocol implementation
    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return self._name

    def is_configured(self) -> bool:
        """Mock is always configured unless set to fail."""
        return not self._should_fail

    def get_provider_accounts(self) -> list[ProviderAccount]:
        """Return mock accounts in ProviderAccount format."""
        if self._should_fail:
            self._raise_failure()
        return [
            ProviderAccount(
                id=acc.id,
                name=acc.name,
                institution=acc.brokerage_name,
                account_number=acc.account_number,
            )
            for acc in self._accounts
        ]

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Return mock holdings in ProviderHolding format."""
        if self._should_fail:
            self._raise_failure()

        holdings = self._holdings
        if account_id:
            holdings = [h for h in holdings if h.account_id == account_id]

        return [
            ProviderHolding(
                account_id=h.account_id,
                symbol=h.symbol,
                quantity=Decimal(str(h.quantity)),
                price=Decimal(str(h.price)),
                market_value=Decimal(str(h.market_value)),
                currency=h.currency,
                name=None,
            )
            for h in holdings
        ]

    def sync_all(self) -> ProviderSyncResult:
        """Return mock sync result with accounts and activities."""
        holdings = self.get_holdings()
        accounts = self.get_provider_accounts()
        return ProviderSyncResult(
            holdings=holdings,
            accounts=accounts,
            errors=[],
            balance_dates=self._balance_dates,
            activities=self._activities,
        )

    # Legacy SnapTradeClientProtocol implementation
    def get_accounts(self) -> list[SnapTradeAccount]:
        """Return mock accounts or raise an error."""
        if self._should_fail:
            self._raise_failure()
        return self._accounts

    def get_all_holdings(self) -> list[SnapTradeHolding]:
        """Return mock holdings or raise an error."""
        if self._should_fail:
            self._raise_failure()
        return self._holdings


class MockProviderRegistry(ProviderRegistry):
    """Mock provider registry for testing.

    Allows injecting mock providers without going through initialization.
    """

    def __init__(self, providers: dict | None = None):
        """Initialize with optional pre-configured providers.

        Args:
            providers: Dict mapping provider name to ProviderClient.
                      If None, starts empty.
        """
        super().__init__()
        if providers:
            for name, provider in providers.items():
                self._providers[name] = provider

    def initialize_default_providers(self) -> None:
        """Override to do nothing - tests configure providers explicitly."""
        pass


def _coerce_errors(errors: list[str | ProviderSyncError] | None) -> list[ProviderSyncError]:
    """Convert a mixed list of strings and ProviderSyncError to all ProviderSyncError.

    Parses SimpleFIN-style error strings (e.g., "Connection to X may need attention")
    into ProviderSyncError objects with institution_name populated, matching the
    behavior of SimpleFINClient._parse_simplefin_errors().
    """
    import re

    if not errors:
        return []

    pattern = re.compile(
        r"connection to (.+?) may need attention", re.IGNORECASE
    )
    result = []
    for e in errors:
        if isinstance(e, ProviderSyncError):
            result.append(e)
        else:
            msg = str(e)
            match = pattern.search(msg)
            if match:
                result.append(ProviderSyncError(
                    message=msg,
                    category=ErrorCategory.CONNECTION,
                    institution_name=match.group(1).strip(),
                    retriable=True,
                ))
            else:
                result.append(ProviderSyncError(message=msg))
    return result


class MockSimpleFINClient:
    """Mock SimpleFIN client for testing.

    Implements the ProviderClient protocol.
    """

    def __init__(
        self,
        accounts: list[dict] | None = None,
        holdings: list[dict] | None = None,
        should_fail: bool = False,
        failure_message: str = "Mock SimpleFIN error",
        failure_type: str = "generic",
        errors: list[str | ProviderSyncError] | None = None,
        balance_dates: dict[str, datetime | None] | None = None,
        activities: list[ProviderActivity] | None = None,
    ):
        self._accounts = accounts or []
        self._holdings = holdings or []
        self._should_fail = should_fail
        self._failure_message = failure_message
        self._failure_type = failure_type
        self._errors = _coerce_errors(errors)
        self._balance_dates = balance_dates or {}
        self._activities = activities or []

    def _raise_failure(self) -> None:
        """Raise the appropriate exception based on failure_type."""
        if self._failure_type == "auth":
            raise ProviderAuthError(self._failure_message, provider_name="SimpleFIN")
        elif self._failure_type == "connection":
            raise ProviderConnectionError(self._failure_message, provider_name="SimpleFIN")
        else:
            raise Exception(self._failure_message)

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "SimpleFIN"

    def is_configured(self) -> bool:
        """Mock is always configured unless set to fail."""
        return not self._should_fail

    def get_accounts(self) -> list[ProviderAccount]:
        """Return mock accounts in ProviderAccount format."""
        if self._should_fail:
            self._raise_failure()
        return [
            ProviderAccount(
                id=acc["id"],
                name=acc["name"],
                institution=acc.get("org", {}).get("name", "Unknown"),
                account_number=None,
            )
            for acc in self._accounts
        ]

    def get_provider_accounts(self) -> list[ProviderAccount]:
        """Alias for get_accounts."""
        return self.get_accounts()

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Return mock holdings in ProviderHolding format.

        Matches real SimpleFINClient behavior: generates synthetic symbols
        for holdings without ticker symbols, skipping zero-value ones,
        and derives cash from balance minus holdings total.
        """
        if self._should_fail:
            self._raise_failure()

        result = []
        for acc in self._accounts:
            if account_id and acc["id"] != account_id:
                continue

            account_holdings = []
            for h in acc.get("holdings", []):
                # Handle missing symbol - generate synthetic or skip
                symbol = h.get("symbol")
                if not symbol:
                    holding_id = h.get("id")
                    if not holding_id:
                        # Cannot create stable symbol without ID
                        continue
                    # Skip zero-value holdings without symbols
                    market_value_raw = h.get("market_value", 0)
                    if not market_value_raw or Decimal(str(market_value_raw)) <= 0:
                        continue
                    symbol = _generate_synthetic_symbol(holding_id)

                quantity = Decimal(str(h.get("quantity", 0)))
                market_value = Decimal(str(h.get("market_value", 0)))
                price = market_value / quantity if quantity > 0 else Decimal(0)
                account_holdings.append(
                    ProviderHolding(
                        account_id=acc["id"],
                        symbol=symbol,
                        quantity=quantity,
                        price=price,
                        market_value=market_value,
                        currency=h.get("currency", "USD"),
                        name=h.get("description"),
                    )
                )

            result.extend(account_holdings)

            # Derive cash from balance minus holdings total (matching real client)
            balance_raw = acc.get("balance")
            if balance_raw is not None:
                try:
                    balance = Decimal(str(balance_raw))
                    holdings_total = sum(h.market_value for h in account_holdings)
                    cash = balance - holdings_total
                    if cash != 0:
                        currency = acc.get("currency", "USD") or "USD"
                        result.append(
                            ProviderHolding(
                                account_id=acc["id"],
                                symbol=f"_CASH:{currency}",
                                quantity=cash,
                                price=Decimal("1"),
                                market_value=cash,
                                currency=currency,
                                name=f"{currency} Cash",
                            )
                        )
                except Exception:
                    pass

        return result

    def sync_all(self) -> ProviderSyncResult:
        """Return mock sync result with accounts, activities, errors, and balance dates."""
        holdings = self.get_holdings()
        accounts = self.get_accounts()
        return ProviderSyncResult(
            holdings=holdings,
            accounts=accounts,
            errors=self._errors,
            balance_dates=self._balance_dates,
            activities=self._activities,
        )


# Sample test data
SAMPLE_SNAPTRADE_ACCOUNTS = [
    SnapTradeAccount(
        id="st_acc_001",
        name="My Brokerage Account",
        brokerage_name="Interactive Brokers",
        account_number="U1234567",
    ),
    SnapTradeAccount(
        id="st_acc_002",
        name="401k Account",
        brokerage_name="Fidelity",
        account_number="X9876543",
    ),
]

SAMPLE_SNAPTRADE_HOLDINGS = [
    SnapTradeHolding(
        account_id="st_acc_001",
        symbol="AAPL",
        quantity=100.0,
        price=150.50,
        market_value=15050.0,
        currency="USD",
    ),
    SnapTradeHolding(
        account_id="st_acc_001",
        symbol="GOOGL",
        quantity=50.0,
        price=140.25,
        market_value=7012.50,
        currency="USD",
    ),
    SnapTradeHolding(
        account_id="st_acc_002",
        symbol="VTI",
        quantity=200.0,
        price=220.00,
        market_value=44000.0,
        currency="USD",
    ),
]

# Sample SimpleFIN test data (dict format matching API response)
SAMPLE_SIMPLEFIN_ACCOUNTS = [
    {
        "id": "sf_acc_001",
        "name": "Checking Account",
        "org": {"name": "Chase Bank", "domain": "chase.com"},
        "balance": "5000.00",
        "currency": "USD",
        "holdings": [],  # Bank accounts typically don't have holdings
    },
    {
        "id": "sf_acc_002",
        "name": "Investment Account",
        "org": {"name": "Schwab", "domain": "schwab.com"},
        "balance": "75000.00",
        "currency": "USD",
        "holdings": [
            {
                "id": "sf_hold_001",
                "symbol": "SPY",
                "quantity": 100.0,
                "market_value": 45000.00,
                "currency": "USD",
                "description": "SPDR S&P 500 ETF Trust",
            },
            {
                "id": "sf_hold_002",
                "symbol": "BND",
                "quantity": 150.0,
                "market_value": 12000.00,
                "currency": "USD",
                "description": "Vanguard Total Bond Market ETF",
            },
        ],
    },
    {
        "id": "sf_acc_003",
        "name": "Retirement Account",
        "org": {"name": "Vanguard", "domain": "vanguard.com"},
        "balance": "50000.00",
        "currency": "USD",
        "holdings": [
            {
                # Holding without symbol - will get synthetic symbol
                "id": "sf_hold_target_2045",
                "symbol": None,
                "quantity": 500.0,
                "market_value": 25000.00,
                "currency": "USD",
                "description": "Vanguard Target Retirement 2045 Fund",
            },
            {
                # Holding without symbol - 529 plan
                "id": "sf_hold_529_growth",
                "symbol": None,
                "quantity": 200.0,
                "market_value": 15000.00,
                "currency": "USD",
                "description": "State 529 Growth Portfolio",
            },
            {
                "id": "sf_hold_003",
                "symbol": "VXUS",
                "quantity": 100.0,
                "market_value": 10000.00,
                "currency": "USD",
                "description": "Vanguard Total International Stock ETF",
            },
        ],
    },
]


class MockIBKRFlexClient:
    """Mock IBKR Flex client for testing.

    Implements the ProviderClient protocol. Accepts ProviderAccount,
    ProviderHolding, and ProviderActivity lists directly (IBKR data
    is already normalized by the real client).
    """

    def __init__(
        self,
        accounts: list[ProviderAccount] | None = None,
        holdings: list[ProviderHolding] | None = None,
        activities: list[ProviderActivity] | None = None,
        balance_dates: dict[str, datetime | None] | None = None,
        should_fail: bool = False,
        failure_type: str = "generic",
        errors: list[str | ProviderSyncError] | None = None,
    ):
        self._accounts = accounts or []
        self._holdings = holdings or []
        self._activities = activities or []
        self._balance_dates = balance_dates or {}
        self._should_fail = should_fail
        self._failure_type = failure_type
        self._errors = _coerce_errors(errors)

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "IBKR"

    def is_configured(self) -> bool:
        """Mock is always configured unless set to fail."""
        return not self._should_fail

    def _raise_failure(self) -> None:
        """Raise the appropriate exception based on failure_type."""
        if self._failure_type == "auth":
            raise ProviderAuthError("Mock IBKR error", provider_name="IBKR")
        elif self._failure_type == "connection":
            raise ProviderConnectionError("Mock IBKR error", provider_name="IBKR")
        else:
            raise Exception("Mock IBKR error")

    def get_accounts(self) -> list[ProviderAccount]:
        """Return mock accounts."""
        if self._should_fail:
            self._raise_failure()
        return list(self._accounts)

    def get_provider_accounts(self) -> list[ProviderAccount]:
        """Alias for get_accounts."""
        return self.get_accounts()

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Return mock holdings, optionally filtered by account."""
        if self._should_fail:
            self._raise_failure()
        if account_id:
            return [h for h in self._holdings if h.account_id == account_id]
        return list(self._holdings)

    def sync_all(self) -> ProviderSyncResult:
        """Return mock sync result."""
        if self._should_fail:
            self._raise_failure()
        return ProviderSyncResult(
            holdings=list(self._holdings),
            accounts=list(self._accounts),
            errors=list(self._errors),
            balance_dates=dict(self._balance_dates),
            activities=list(self._activities),
        )


# Sample IBKR test data (ProviderAccount/ProviderHolding/ProviderActivity format)
SAMPLE_IBKR_ACCOUNTS = [
    ProviderAccount(
        id="ib_acc_001",
        name="My Trading Account",
        institution="Interactive Brokers",
        account_number=None,
    ),
    ProviderAccount(
        id="ib_acc_002",
        name="Interactive Brokers IRA Account",
        institution="Interactive Brokers",
        account_number=None,
    ),
]

SAMPLE_IBKR_HOLDINGS = [
    ProviderHolding(
        account_id="ib_acc_001",
        symbol="AAPL",
        quantity=Decimal("100"),
        price=Decimal("175.50"),
        market_value=Decimal("17550.00"),
        currency="USD",
        name="Apple Inc",
    ),
    ProviderHolding(
        account_id="ib_acc_001",
        symbol="MSFT",
        quantity=Decimal("50"),
        price=Decimal("380.00"),
        market_value=Decimal("19000.00"),
        currency="USD",
        name="Microsoft Corp",
    ),
    ProviderHolding(
        account_id="ib_acc_001",
        symbol="_CASH:USD",
        quantity=Decimal("5432.10"),
        price=Decimal("1"),
        market_value=Decimal("5432.10"),
        currency="USD",
        name="USD Cash",
    ),
    ProviderHolding(
        account_id="ib_acc_002",
        symbol="VTI",
        quantity=Decimal("200"),
        price=Decimal("220.00"),
        market_value=Decimal("44000.00"),
        currency="USD",
        name="Vanguard Total Stock Market ETF",
    ),
    ProviderHolding(
        account_id="ib_acc_002",
        symbol="_CASH:USD",
        quantity=Decimal("1000.00"),
        price=Decimal("1"),
        market_value=Decimal("1000.00"),
        currency="USD",
        name="USD Cash",
    ),
]

SAMPLE_IBKR_ACTIVITIES = [
    ProviderActivity(
        account_id="ib_acc_001",
        external_id="T001",
        activity_date=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        type="buy",
        amount=Decimal("-17000.00"),
        description="Buy 100 AAPL",
        ticker="AAPL",
        units=Decimal("100"),
        price=Decimal("170.00"),
        currency="USD",
        fee=Decimal("-1.00"),
    ),
    ProviderActivity(
        account_id="ib_acc_001",
        external_id="T002",
        activity_date=datetime(2026, 1, 20, 14, 0, 0, tzinfo=timezone.utc),
        type="sell",
        amount=Decimal("3500.00"),
        description="Sell 25 GOOGL",
        ticker="GOOGL",
        units=Decimal("-25"),
        price=Decimal("140.00"),
        currency="USD",
        fee=Decimal("-1.00"),
    ),
    ProviderActivity(
        account_id="ib_acc_001",
        external_id="CT:CT001",
        activity_date=datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc),
        type="dividend",
        amount=Decimal("25.50"),
        description="AAPL(US0378331005) CASH DIVIDEND",
        ticker="AAPL",
        units=None,
        price=None,
        currency="USD",
        fee=None,
    ),
    ProviderActivity(
        account_id="ib_acc_001",
        external_id="CT:CT002",
        activity_date=datetime(2026, 2, 5, 9, 0, 0, tzinfo=timezone.utc),
        type="deposit",
        amount=Decimal("10000.00"),
        description="ELECTRONIC FUND TRANSFER",
        ticker=None,
        units=None,
        price=None,
        currency="USD",
        fee=None,
    ),
    ProviderActivity(
        account_id="ib_acc_001",
        external_id="CT:CT003",
        activity_date=datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc),
        type="interest",
        amount=Decimal("12.34"),
        description="USD CREDIT INT FOR JAN-2026",
        ticker=None,
        units=None,
        price=None,
        currency="USD",
        fee=None,
    ),
]


class MockCoinbaseClient:
    """Mock Coinbase client for testing.

    Implements the ProviderClient protocol. Accepts ProviderAccount,
    ProviderHolding, and ProviderActivity lists directly (Coinbase data
    is already normalized by the real client).
    """

    def __init__(
        self,
        accounts: list[ProviderAccount] | None = None,
        holdings: list[ProviderHolding] | None = None,
        activities: list[ProviderActivity] | None = None,
        balance_dates: dict[str, datetime | None] | None = None,
        should_fail: bool = False,
        failure_type: str = "generic",
        errors: list[str | ProviderSyncError] | None = None,
    ):
        self._accounts = accounts or []
        self._holdings = holdings or []
        self._activities = activities or []
        self._balance_dates = balance_dates or {}
        self._should_fail = should_fail
        self._failure_type = failure_type
        self._errors = _coerce_errors(errors)

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "Coinbase"

    def is_configured(self) -> bool:
        """Mock is always configured unless set to fail."""
        return not self._should_fail

    def _raise_failure(self) -> None:
        """Raise the appropriate exception based on failure_type."""
        if self._failure_type == "auth":
            raise ProviderAuthError("Mock Coinbase error", provider_name="Coinbase")
        elif self._failure_type == "connection":
            raise ProviderConnectionError("Mock Coinbase error", provider_name="Coinbase")
        else:
            raise Exception("Mock Coinbase error")

    def get_accounts(self) -> list[ProviderAccount]:
        """Return mock accounts."""
        if self._should_fail:
            self._raise_failure()
        return list(self._accounts)

    def get_provider_accounts(self) -> list[ProviderAccount]:
        """Alias for get_accounts."""
        return self.get_accounts()

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Return mock holdings, optionally filtered by account."""
        if self._should_fail:
            self._raise_failure()
        if account_id:
            return [h for h in self._holdings if h.account_id == account_id]
        return list(self._holdings)

    def sync_all(self) -> ProviderSyncResult:
        """Return mock sync result."""
        if self._should_fail:
            self._raise_failure()
        return ProviderSyncResult(
            holdings=list(self._holdings),
            accounts=list(self._accounts),
            errors=list(self._errors),
            balance_dates=dict(self._balance_dates),
            activities=list(self._activities),
        )


# Sample Coinbase test data (ProviderAccount/ProviderHolding/ProviderActivity format)
SAMPLE_COINBASE_ACCOUNTS = [
    ProviderAccount(
        id="cb_port_001",
        name="Default Portfolio",
        institution="Coinbase",
        account_number=None,
    ),
]

SAMPLE_COINBASE_HOLDINGS = [
    ProviderHolding(
        account_id="cb_port_001",
        symbol="BTC",
        quantity=Decimal("0.5"),
        price=Decimal("60000"),
        market_value=Decimal("30000"),
        currency="USD",
        name="BTC",
    ),
    ProviderHolding(
        account_id="cb_port_001",
        symbol="ETH",
        quantity=Decimal("5.0"),
        price=Decimal("3000"),
        market_value=Decimal("15000"),
        currency="USD",
        name="ETH",
    ),
    ProviderHolding(
        account_id="cb_port_001",
        symbol="_CASH:USD",
        quantity=Decimal("2500"),
        price=Decimal("1"),
        market_value=Decimal("2500"),
        currency="USD",
        name="USD Cash",
    ),
]

class MockSchwabClient:
    """Mock Schwab client for testing.

    Implements the ProviderClient protocol. Accepts ProviderAccount,
    ProviderHolding, and ProviderActivity lists directly (Schwab data
    is already normalized by the real client).
    """

    def __init__(
        self,
        accounts: list[ProviderAccount] | None = None,
        holdings: list[ProviderHolding] | None = None,
        activities: list[ProviderActivity] | None = None,
        balance_dates: dict[str, datetime | None] | None = None,
        should_fail: bool = False,
        failure_type: str = "generic",
        errors: list[str | ProviderSyncError] | None = None,
    ):
        self._accounts = accounts or []
        self._holdings = holdings or []
        self._activities = activities or []
        self._balance_dates = balance_dates or {}
        self._should_fail = should_fail
        self._failure_type = failure_type
        self._errors = _coerce_errors(errors)

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "Schwab"

    def is_configured(self) -> bool:
        """Mock is always configured unless set to fail."""
        return not self._should_fail

    def _raise_failure(self) -> None:
        """Raise the appropriate exception based on failure_type."""
        if self._failure_type == "auth":
            raise ProviderAuthError("Mock Schwab error", provider_name="Schwab")
        elif self._failure_type == "connection":
            raise ProviderConnectionError("Mock Schwab error", provider_name="Schwab")
        else:
            raise Exception("Mock Schwab error")

    def get_accounts(self) -> list[ProviderAccount]:
        """Return mock accounts."""
        if self._should_fail:
            self._raise_failure()
        return list(self._accounts)

    def get_provider_accounts(self) -> list[ProviderAccount]:
        """Alias for get_accounts."""
        return self.get_accounts()

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Return mock holdings, optionally filtered by account."""
        if self._should_fail:
            self._raise_failure()
        if account_id:
            return [h for h in self._holdings if h.account_id == account_id]
        return list(self._holdings)

    def sync_all(self) -> ProviderSyncResult:
        """Return mock sync result."""
        if self._should_fail:
            self._raise_failure()
        return ProviderSyncResult(
            holdings=list(self._holdings),
            accounts=list(self._accounts),
            errors=list(self._errors),
            balance_dates=dict(self._balance_dates),
            activities=list(self._activities),
        )


SAMPLE_COINBASE_ACTIVITIES = [
    ProviderActivity(
        account_id="cb_port_001",
        external_id="fill_001",
        activity_date=datetime(2026, 1, 10, 9, 0, 0, tzinfo=timezone.utc),
        type="buy",
        amount=Decimal("-30000.00"),
        description="BUY BTC on Coinbase",
        ticker="BTC",
        units=Decimal("0.5"),
        price=Decimal("60000"),
        currency="USD",
        fee=Decimal("-10.00"),
    ),
    ProviderActivity(
        account_id="cb_port_001",
        external_id="fill_002",
        activity_date=datetime(2026, 1, 12, 14, 30, 0, tzinfo=timezone.utc),
        type="sell",
        amount=Decimal("6200.00"),
        description="SELL ETH on Coinbase",
        ticker="ETH",
        units=Decimal("2.0"),
        price=Decimal("3100"),
        currency="USD",
        fee=Decimal("-8.00"),
    ),
    ProviderActivity(
        account_id="cb_port_001",
        external_id="v2:recv-001",
        activity_date=datetime(2026, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
        type="deposit",
        amount=Decimal("6000.00"),
        description="Received BTC",
        ticker="BTC",
        units=Decimal("0.1"),
        price=Decimal("60000"),
        currency="USD",
        fee=None,
    ),
]


# Sample Schwab test data (ProviderAccount/ProviderHolding/ProviderActivity format)
SAMPLE_SCHWAB_ACCOUNTS = [
    ProviderAccount(
        id="HASH_ABC",
        name="Schwab Individual Account",
        institution="Charles Schwab",
        account_number="12345678",
    ),
    ProviderAccount(
        id="HASH_DEF",
        name="Schwab Margin Account",
        institution="Charles Schwab",
        account_number="87654321",
    ),
]

SAMPLE_SCHWAB_HOLDINGS = [
    ProviderHolding(
        account_id="HASH_ABC",
        symbol="AAPL",
        quantity=Decimal("100"),
        price=Decimal("150.25"),
        market_value=Decimal("15025.00"),
        currency="USD",
        name="APPLE INC",
    ),
    ProviderHolding(
        account_id="HASH_ABC",
        symbol="GOOGL",
        quantity=Decimal("50"),
        price=Decimal("140.00"),
        market_value=Decimal("7000.00"),
        currency="USD",
        name="ALPHABET INC",
    ),
    ProviderHolding(
        account_id="HASH_ABC",
        symbol="_CASH:USD",
        quantity=Decimal("5000.00"),
        price=Decimal("1"),
        market_value=Decimal("5000.00"),
        currency="USD",
        name="USD Cash",
    ),
    ProviderHolding(
        account_id="HASH_DEF",
        symbol="MSFT",
        quantity=Decimal("200"),
        price=Decimal("400.00"),
        market_value=Decimal("80000.00"),
        currency="USD",
        name="MICROSOFT CORP",
    ),
    ProviderHolding(
        account_id="HASH_DEF",
        symbol="_CASH:USD",
        quantity=Decimal("1000.00"),
        price=Decimal("1"),
        market_value=Decimal("1000.00"),
        currency="USD",
        name="USD Cash",
    ),
]

class MockPlaidClient:
    """Mock Plaid client for testing.

    Implements the ProviderClient protocol. Accepts ProviderAccount,
    ProviderHolding, and ProviderActivity lists directly (Plaid data
    is already normalized by the real client).
    """

    def __init__(
        self,
        accounts: list[ProviderAccount] | None = None,
        holdings: list[ProviderHolding] | None = None,
        activities: list[ProviderActivity] | None = None,
        balance_dates: dict[str, datetime | None] | None = None,
        should_fail: bool = False,
        failure_type: str = "generic",
        errors: list[str | ProviderSyncError] | None = None,
        link_token: str = "link-sandbox-test-token",
        exchange_result: dict | None = None,
    ):
        self._accounts = accounts or []
        self._holdings = holdings or []
        self._activities = activities or []
        self._balance_dates = balance_dates or {}
        self._should_fail = should_fail
        self._failure_type = failure_type
        self._errors = _coerce_errors(errors)
        self._link_token = link_token
        self._exchange_result = exchange_result or {
            "access_token": "access-sandbox-test",
            "item_id": "item-sandbox-test",
        }

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "Plaid"

    def is_configured(self) -> bool:
        """Mock is always configured unless set to fail."""
        return not self._should_fail

    def _raise_failure(self) -> None:
        """Raise the appropriate exception based on failure_type."""
        if self._failure_type == "auth":
            raise ProviderAuthError("Mock Plaid error", provider_name="Plaid")
        elif self._failure_type == "connection":
            raise ProviderConnectionError("Mock Plaid error", provider_name="Plaid")
        else:
            raise Exception("Mock Plaid error")

    def create_link_token(self) -> str:
        """Return mock link token."""
        if self._should_fail:
            self._raise_failure()
        return self._link_token

    def exchange_public_token(self, public_token: str) -> dict:
        """Return mock exchange result."""
        if self._should_fail:
            self._raise_failure()
        return dict(self._exchange_result)

    def remove_item(self, access_token: str) -> None:
        """Mock item removal (no-op)."""
        if self._should_fail:
            self._raise_failure()

    def get_accounts(self) -> list[ProviderAccount]:
        """Return mock accounts."""
        if self._should_fail:
            self._raise_failure()
        return list(self._accounts)

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        """Return mock holdings, optionally filtered by account."""
        if self._should_fail:
            self._raise_failure()
        if account_id:
            return [h for h in self._holdings if h.account_id == account_id]
        return list(self._holdings)

    def sync_all(
        self,
        access_tokens: list[tuple[str, str]] | None = None,
    ) -> ProviderSyncResult:
        """Return mock sync result."""
        if self._should_fail:
            self._raise_failure()
        return ProviderSyncResult(
            holdings=list(self._holdings),
            accounts=list(self._accounts),
            errors=list(self._errors),
            balance_dates=dict(self._balance_dates),
            activities=list(self._activities),
        )


# Sample Plaid test data
SAMPLE_PLAID_ACCOUNTS = [
    ProviderAccount(
        id="plaid_acc_001",
        name="Plaid Checking",
        institution="Chase",
        account_number="1234",
    ),
    ProviderAccount(
        id="plaid_acc_002",
        name="Plaid Investment",
        institution="Vanguard",
        account_number="5678",
    ),
]

SAMPLE_PLAID_HOLDINGS = [
    ProviderHolding(
        account_id="plaid_acc_002",
        symbol="VTI",
        quantity=Decimal("100"),
        price=Decimal("220.00"),
        market_value=Decimal("22000.00"),
        currency="USD",
        name="Vanguard Total Stock Market ETF",
    ),
    ProviderHolding(
        account_id="plaid_acc_002",
        symbol="_CASH:USD",
        quantity=Decimal("3000.00"),
        price=Decimal("1"),
        market_value=Decimal("3000.00"),
        currency="USD",
        name="USD Cash",
    ),
]

SAMPLE_PLAID_ACTIVITIES = [
    ProviderActivity(
        account_id="plaid_acc_002",
        external_id="plaid_txn_001",
        activity_date=datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        type="buy",
        amount=Decimal("-22000.00"),
        description="Buy 100 VTI",
        ticker="VTI",
        units=Decimal("100"),
        price=Decimal("220.00"),
        currency="USD",
        fee=None,
    ),
]


class MockMarketDataProvider:
    """Mock market data provider for testing.

    Implements the MarketDataProvider protocol using an in-memory dict.
    """

    def __init__(
        self,
        prices: dict[str, list[PriceResult]] | None = None,
        should_fail: bool = False,
    ):
        self._prices = prices or {}
        self._should_fail = should_fail

    @property
    def provider_name(self) -> str:
        return "mock"

    def get_price_history(
        self, symbols: list[str], start_date: date, end_date: date
    ) -> dict[str, list[PriceResult]]:
        if self._should_fail:
            raise Exception("Mock market data error")
        result: dict[str, list[PriceResult]] = {}
        for symbol in symbols:
            result[symbol] = [
                pr
                for pr in self._prices.get(symbol, [])
                if start_date <= pr.price_date <= end_date
            ]
        return result


SAMPLE_SCHWAB_ACTIVITIES = [
    ProviderActivity(
        account_id="HASH_ABC",
        external_id="111222333",
        activity_date=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        type="buy",
        amount=Decimal("-15025.00"),
        description="APPLE INC",
        ticker="AAPL",
        units=Decimal("100"),
        price=Decimal("150.25"),
        currency="USD",
        fee=None,
    ),
    ProviderActivity(
        account_id="HASH_ABC",
        external_id="444555666",
        activity_date=datetime(2026, 1, 20, 0, 0, 0, tzinfo=timezone.utc),
        type="dividend",
        amount=Decimal("25.50"),
        description="DIVIDEND PAYMENT",
        ticker="AAPL",
        units=None,
        price=None,
        currency="USD",
        fee=None,
    ),
    ProviderActivity(
        account_id="HASH_DEF",
        external_id="777888999",
        activity_date=datetime(2026, 1, 22, 14, 0, 0, tzinfo=timezone.utc),
        type="sell",
        amount=Decimal("40000.00"),
        description="MICROSOFT CORP",
        ticker="MSFT",
        units=Decimal("100"),
        price=Decimal("400.00"),
        currency="USD",
        fee=Decimal("0.65"),
    ),
]
