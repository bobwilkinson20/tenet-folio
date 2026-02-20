"""External API integrations.

This package contains:
- Provider protocol: Common interface for data aggregation providers
- Provider registry: Manages multiple providers
- SnapTrade client: Integration with SnapTrade API
- (Future) SimpleFIN client: Integration with SimpleFIN API
"""

from integrations.provider_protocol import (
    ProviderAccount,
    ProviderClient,
    ProviderHolding,
)
from integrations.provider_registry import ProviderRegistry, get_provider_registry

__all__ = [
    "ProviderAccount",
    "ProviderClient",
    "ProviderHolding",
    "ProviderRegistry",
    "get_provider_registry",
]
