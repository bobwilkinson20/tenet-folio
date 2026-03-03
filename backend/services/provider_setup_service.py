"""Compatibility shim — re-exports from services.provider_setup package.

Existing imports in ``api.providers`` and ``services.provider_service``
continue to work without modification.
"""

from services.provider_setup import (  # noqa: F401
    PROVIDER_CREDENTIAL_MAP,
    ProviderFieldDef,
    SetupResult,
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
