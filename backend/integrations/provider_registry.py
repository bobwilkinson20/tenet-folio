"""Provider registry for managing multiple data aggregation providers.

The registry is responsible for:
- Initializing and tracking available providers
- Providing access to specific providers by name
- Listing all configured providers
"""

import importlib
import logging

from integrations.provider_protocol import ProviderClient

logger = logging.getLogger(__name__)

# Each tuple is (provider_name, module_path, class_name).
# Adding a new provider only requires appending one entry here.
PROVIDER_DEFINITIONS: list[tuple[str, str, str]] = [
    ("SnapTrade", "integrations.snaptrade_client", "SnapTradeClient"),
    ("SimpleFIN", "integrations.simplefin_client", "SimpleFINClient"),
    ("IBKR", "integrations.ibkr_flex_client", "IBKRFlexClient"),
    ("Coinbase", "integrations.coinbase_client", "CoinbaseClient"),
    ("Schwab", "integrations.schwab_client", "SchwabClient"),
]

ALL_PROVIDER_NAMES: list[str] = [name for name, _, _ in PROVIDER_DEFINITIONS]


class ProviderRegistry:
    """Registry for managing multiple data aggregation providers.

    This class manages the lifecycle of provider clients and provides
    a unified interface for accessing them.

    Example:
        registry = ProviderRegistry()
        if registry.is_configured("SnapTrade"):
            provider = registry.get_provider("SnapTrade")
            accounts = provider.get_accounts()
    """

    def __init__(self):
        """Initialize the registry with no providers.

        Call register_provider() to add providers, or use
        initialize_default_providers() to auto-detect configured providers.
        """
        self._providers: dict[str, ProviderClient] = {}

    def register_provider(self, provider: ProviderClient) -> None:
        """Register a provider client.

        Args:
            provider: A provider client implementing ProviderClient protocol.
        """
        self._providers[provider.provider_name] = provider

    def get_provider(self, name: str) -> ProviderClient:
        """Get a provider by name.

        Args:
            name: The provider name (e.g., 'SnapTrade', 'SimpleFIN').

        Returns:
            The provider client.

        Raises:
            ValueError: If the provider is not registered/configured.
        """
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' is not configured")
        return self._providers[name]

    def list_providers(self) -> list[str]:
        """List all registered provider names.

        Returns:
            List of provider names that are currently registered.
        """
        return list(self._providers.keys())

    def is_configured(self, name: str) -> bool:
        """Check if a provider is registered and configured.

        Args:
            name: The provider name to check.

        Returns:
            True if the provider is registered, False otherwise.
        """
        return name in self._providers

    def initialize_default_providers(self) -> None:
        """Auto-detect and initialize all configured providers.

        This method attempts to initialize each known provider type
        and registers only those that have valid credentials configured.
        Each import is wrapped in try/except so a missing dependency for
        one provider never prevents the rest from initializing.
        """
        for name, module_path, class_name in PROVIDER_DEFINITIONS:
            try:
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                self._try_init_provider(name, cls)
            except ImportError:
                logger.debug("Provider skipped (not installed): %s", name)

        names = self.list_providers()
        if names:
            logger.info("Active providers: %s", ", ".join(names))
        else:
            logger.warning("No providers configured")

    def _try_init_provider(self, name: str, cls: type) -> None:
        """Attempt to instantiate and register a single provider.

        Args:
            name: Display name for logging.
            cls: Provider client class to instantiate.
        """
        try:
            instance = cls()
            if instance.is_configured():
                self.register_provider(instance)
                logger.info("Provider registered: %s", name)
            else:
                logger.debug("Provider skipped (not configured): %s", name)
        except Exception:
            logger.warning(
                "Provider failed to initialize: %s", name, exc_info=True
            )


def get_provider_registry() -> ProviderRegistry:
    """Create and return a provider registry with default providers.

    This is a factory function that creates a new registry instance
    and initializes it with all configured providers.

    Returns:
        A ProviderRegistry with all available providers registered.
    """
    registry = ProviderRegistry()
    registry.initialize_default_providers()
    return registry
