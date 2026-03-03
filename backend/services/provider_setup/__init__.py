"""Provider setup package — in-app credential configuration for data providers.

Re-exports the public API so consumers can import from
``services.provider_setup`` directly.
"""

from .base import ProviderFieldDef, SetupResult
from .registry import (
    PROVIDER_CREDENTIAL_MAP,
    get_setup_fields,
    remove_credentials,
    validate_and_store,
)

__all__ = [
    "PROVIDER_CREDENTIAL_MAP",
    "ProviderFieldDef",
    "SetupResult",
    "get_setup_fields",
    "remove_credentials",
    "validate_and_store",
]
