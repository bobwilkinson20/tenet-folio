"""Unit tests for the provider registry and protocol."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from integrations.provider_protocol import ProviderAccount, ProviderHolding
from integrations.provider_registry import (
    ALL_PROVIDER_NAMES,
    PROVIDER_DEFINITIONS,
    ProviderRegistry,
)


class MockProvider:
    """Mock provider for testing."""

    def __init__(
        self,
        name: str = "MockProvider",
        configured: bool = True,
        accounts: list[ProviderAccount] | None = None,
        holdings: list[ProviderHolding] | None = None,
    ):
        self._name = name
        self._configured = configured
        self._accounts = accounts or []
        self._holdings = holdings or []

    @property
    def provider_name(self) -> str:
        return self._name

    def is_configured(self) -> bool:
        return self._configured

    def get_accounts(self) -> list[ProviderAccount]:
        return self._accounts

    def get_holdings(self, account_id: str | None = None) -> list[ProviderHolding]:
        if account_id:
            return [h for h in self._holdings if h.account_id == account_id]
        return self._holdings


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    def test_empty_registry(self):
        """A new registry has no providers."""
        registry = ProviderRegistry()
        assert registry.list_providers() == []

    def test_register_provider(self):
        """Can register a provider."""
        registry = ProviderRegistry()
        provider = MockProvider(name="TestProvider")

        registry.register_provider(provider)

        assert registry.list_providers() == ["TestProvider"]
        assert registry.is_configured("TestProvider")

    def test_register_multiple_providers(self):
        """Can register multiple providers."""
        registry = ProviderRegistry()
        provider1 = MockProvider(name="Provider1")
        provider2 = MockProvider(name="Provider2")

        registry.register_provider(provider1)
        registry.register_provider(provider2)

        assert set(registry.list_providers()) == {"Provider1", "Provider2"}

    def test_get_provider(self):
        """Can retrieve a registered provider."""
        registry = ProviderRegistry()
        provider = MockProvider(name="TestProvider")
        registry.register_provider(provider)

        retrieved = registry.get_provider("TestProvider")

        assert retrieved is provider

    def test_get_provider_not_found(self):
        """Getting an unregistered provider raises ValueError."""
        registry = ProviderRegistry()

        with pytest.raises(ValueError) as exc_info:
            registry.get_provider("NonExistent")

        assert "NonExistent" in str(exc_info.value)
        assert "not configured" in str(exc_info.value)

    def test_is_configured_false_for_missing(self):
        """is_configured returns False for unregistered providers."""
        registry = ProviderRegistry()

        assert not registry.is_configured("NonExistent")

    def test_provider_replaces_existing(self):
        """Registering a provider with same name replaces existing."""
        registry = ProviderRegistry()
        provider1 = MockProvider(name="TestProvider")
        provider2 = MockProvider(name="TestProvider")

        registry.register_provider(provider1)
        registry.register_provider(provider2)

        assert registry.get_provider("TestProvider") is provider2
        assert len(registry.list_providers()) == 1


class TestMockProviderProtocol:
    """Tests verifying MockProvider implements the protocol correctly."""

    def test_provider_name(self):
        """Provider has a name property."""
        provider = MockProvider(name="TestProvider")
        assert provider.provider_name == "TestProvider"

    def test_is_configured(self):
        """Provider reports configuration status."""
        configured = MockProvider(configured=True)
        unconfigured = MockProvider(configured=False)

        assert configured.is_configured()
        assert not unconfigured.is_configured()

    def test_get_accounts(self):
        """Provider returns accounts."""
        accounts = [
            ProviderAccount(
                id="acc1", name="Account 1", institution="Bank A", account_number="123"
            ),
            ProviderAccount(
                id="acc2", name="Account 2", institution="Bank B", account_number=None
            ),
        ]
        provider = MockProvider(accounts=accounts)

        result = provider.get_accounts()

        assert len(result) == 2
        assert result[0].id == "acc1"
        assert result[0].name == "Account 1"
        assert result[0].institution == "Bank A"
        assert result[0].account_number == "123"
        assert result[1].account_number is None

    def test_get_holdings_all(self):
        """Provider returns all holdings when no account_id specified."""
        holdings = [
            ProviderHolding(
                account_id="acc1",
                symbol="AAPL",
                quantity=Decimal("10"),
                price=Decimal("150.00"),
                market_value=Decimal("1500.00"),
                currency="USD",
                name="Apple Inc.",
            ),
            ProviderHolding(
                account_id="acc2",
                symbol="GOOGL",
                quantity=Decimal("5"),
                price=Decimal("140.00"),
                market_value=Decimal("700.00"),
                currency="USD",
                name=None,
            ),
        ]
        provider = MockProvider(holdings=holdings)

        result = provider.get_holdings()

        assert len(result) == 2

    def test_get_holdings_filtered(self):
        """Provider filters holdings by account_id."""
        holdings = [
            ProviderHolding(
                account_id="acc1",
                symbol="AAPL",
                quantity=Decimal("10"),
                price=Decimal("150.00"),
                market_value=Decimal("1500.00"),
                currency="USD",
            ),
            ProviderHolding(
                account_id="acc2",
                symbol="GOOGL",
                quantity=Decimal("5"),
                price=Decimal("140.00"),
                market_value=Decimal("700.00"),
                currency="USD",
            ),
        ]
        provider = MockProvider(holdings=holdings)

        result = provider.get_holdings(account_id="acc1")

        assert len(result) == 1
        assert result[0].symbol == "AAPL"


class TestProviderAccount:
    """Tests for ProviderAccount dataclass."""

    def test_required_fields(self):
        """ProviderAccount requires id, name, institution."""
        account = ProviderAccount(id="123", name="My Account", institution="My Bank")

        assert account.id == "123"
        assert account.name == "My Account"
        assert account.institution == "My Bank"
        assert account.account_number is None

    def test_optional_account_number(self):
        """ProviderAccount accepts optional account_number."""
        account = ProviderAccount(
            id="123", name="My Account", institution="My Bank", account_number="ACC123"
        )

        assert account.account_number == "ACC123"


class TestProviderHolding:
    """Tests for ProviderHolding dataclass."""

    def test_required_fields(self):
        """ProviderHolding requires core fields."""
        holding = ProviderHolding(
            account_id="acc1",
            symbol="AAPL",
            quantity=Decimal("10.5"),
            price=Decimal("150.25"),
            market_value=Decimal("1577.625"),
            currency="USD",
        )

        assert holding.account_id == "acc1"
        assert holding.symbol == "AAPL"
        assert holding.quantity == Decimal("10.5")
        assert holding.price == Decimal("150.25")
        assert holding.market_value == Decimal("1577.625")
        assert holding.currency == "USD"
        assert holding.name is None

    def test_optional_name(self):
        """ProviderHolding accepts optional name."""
        holding = ProviderHolding(
            account_id="acc1",
            symbol="AAPL",
            quantity=Decimal("10"),
            price=Decimal("150.00"),
            market_value=Decimal("1500.00"),
            currency="USD",
            name="Apple Inc.",
        )

        assert holding.name == "Apple Inc."

    def test_decimal_precision(self):
        """ProviderHolding maintains decimal precision."""
        holding = ProviderHolding(
            account_id="acc1",
            symbol="BTC",
            quantity=Decimal("0.00123456"),
            price=Decimal("45678.90123456"),
            market_value=Decimal("56.21319941851"),
            currency="USD",
        )

        assert holding.quantity == Decimal("0.00123456")
        assert holding.price == Decimal("45678.90123456")


class TestProviderDefinitions:
    """Tests for PROVIDER_DEFINITIONS and ALL_PROVIDER_NAMES."""

    def test_definitions_has_five_entries(self):
        """PROVIDER_DEFINITIONS lists all five providers."""
        assert len(PROVIDER_DEFINITIONS) == 5

    def test_definitions_names(self):
        """PROVIDER_DEFINITIONS contains the expected provider names."""
        names = [name for name, _, _ in PROVIDER_DEFINITIONS]
        assert names == ["SnapTrade", "SimpleFIN", "IBKR", "Coinbase", "Schwab"]

    def test_all_provider_names_matches_definitions(self):
        """ALL_PROVIDER_NAMES is derived from PROVIDER_DEFINITIONS."""
        expected = [name for name, _, _ in PROVIDER_DEFINITIONS]
        assert ALL_PROVIDER_NAMES == expected

    def test_definitions_tuples_are_valid(self):
        """Each definition has a non-empty name, module, and class."""
        for name, module_path, class_name in PROVIDER_DEFINITIONS:
            assert name, "Provider name must not be empty"
            assert module_path, "Module path must not be empty"
            assert class_name, "Class name must not be empty"


class TestInitializeDefaultProviders:
    """Tests for data-driven initialize_default_providers."""

    def test_import_error_skips_provider(self):
        """Missing dependency (ImportError) skips that provider, others still register."""
        registry = ProviderRegistry()

        # Mock importlib to raise ImportError for SnapTrade only
        def selective_import(module_path):
            if "snaptrade" in module_path:
                raise ImportError("snaptrade not installed")
            mod = MagicMock()
            mock_cls = MagicMock()
            mock_instance = MagicMock()
            mock_instance.is_configured.return_value = True
            mock_instance.provider_name = module_path.split(".")[-1]
            mock_cls.return_value = mock_instance
            setattr(mod, "SimpleFINClient", mock_cls)
            setattr(mod, "IBKRFlexClient", mock_cls)
            setattr(mod, "CoinbaseClient", mock_cls)
            setattr(mod, "SchwabClient", mock_cls)
            return mod

        with patch("integrations.provider_registry.importlib.import_module", side_effect=selective_import):
            registry.initialize_default_providers()

        # SnapTrade should be skipped, others should be registered
        assert not registry.is_configured("SnapTrade")
        assert len(registry.list_providers()) == 4

    def test_constructor_exception_skips_provider(self):
        """Exception in constructor skips that provider, others still register."""
        registry = ProviderRegistry()

        call_count = 0

        def mock_import(module_path):
            nonlocal call_count
            call_count += 1
            mod = MagicMock()
            mock_cls = MagicMock()
            if "coinbase" in module_path:
                # Simulate constructor exception
                mock_cls.side_effect = RuntimeError("Coinbase init failed")
            else:
                mock_instance = MagicMock()
                mock_instance.is_configured.return_value = True
                mock_instance.provider_name = module_path.split(".")[-1]
                mock_cls.return_value = mock_instance
            # Set class attributes for all possible class names
            for _, _, class_name in PROVIDER_DEFINITIONS:
                setattr(mod, class_name, mock_cls)
            return mod

        with patch("integrations.provider_registry.importlib.import_module", side_effect=mock_import):
            registry.initialize_default_providers()

        # Coinbase should fail, others should be registered
        assert not registry.is_configured("Coinbase")
        assert len(registry.list_providers()) == 4

    def test_loop_iterates_all_definitions(self):
        """The loop calls import_module for each definition."""
        registry = ProviderRegistry()

        imported_modules = []

        def tracking_import(module_path):
            imported_modules.append(module_path)
            mod = MagicMock()
            mock_cls = MagicMock()
            mock_instance = MagicMock()
            mock_instance.is_configured.return_value = False
            mock_cls.return_value = mock_instance
            for _, _, class_name in PROVIDER_DEFINITIONS:
                setattr(mod, class_name, mock_cls)
            return mod

        with patch("integrations.provider_registry.importlib.import_module", side_effect=tracking_import):
            registry.initialize_default_providers()

        expected_modules = [mod for _, mod, _ in PROVIDER_DEFINITIONS]
        assert imported_modules == expected_modules
