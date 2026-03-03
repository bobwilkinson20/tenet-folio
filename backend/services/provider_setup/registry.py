"""Provider setup registry — dispatch logic for setup fields, validation, and removal."""

import logging
from typing import Callable

from schemas.provider import ProviderCredentialInfo
from services.credential_manager import delete_credential

from . import coinbase_setup, ibkr_setup, simplefin_setup
from .base import ProviderFieldDef, SetupResult, sync_setting

logger = logging.getLogger(__name__)

# All provider modules registered for in-app setup.
_PROVIDER_MODULES = [simplefin_setup, ibkr_setup, coinbase_setup]

# Maps provider name → list of credential field definitions.
PROVIDER_CREDENTIAL_MAP: dict[str, list[ProviderFieldDef]] = {
    mod.PROVIDER_NAME: mod.FIELDS for mod in _PROVIDER_MODULES
}

# Dispatch table for provider-specific validators.
_VALIDATORS: dict[
    str, Callable[[dict[str, str], list[ProviderFieldDef]], SetupResult]
] = {mod.PROVIDER_NAME: mod.validate for mod in _PROVIDER_MODULES}


def get_setup_fields(provider_name: str) -> list[ProviderCredentialInfo]:
    """Return the credential field definitions for a provider's setup form.

    Args:
        provider_name: The provider name (e.g., "SimpleFIN").

    Returns:
        List of ProviderCredentialInfo describing each input field.

    Raises:
        ValueError: If the provider is unknown or has no setup fields.
    """
    fields = PROVIDER_CREDENTIAL_MAP.get(provider_name)
    if fields is None:
        raise ValueError(f"No setup configuration for provider: {provider_name}")

    return [
        ProviderCredentialInfo(
            key=f["key"],
            label=f["label"],
            help_text=f["help_text"],
            input_type=f["input_type"],
        )
        for f in fields
    ]


def validate_and_store(provider_name: str, credentials: dict[str, str]) -> SetupResult:
    """Validate credentials and store them in Keychain.

    Args:
        provider_name: The provider name.
        credentials: Dict of field key → value from the setup form.

    Returns:
        SetupResult with success message and optional warnings.

    Raises:
        ValueError: If the provider is unknown or credentials are invalid.
        RuntimeError: If credential storage fails.
    """
    fields = PROVIDER_CREDENTIAL_MAP.get(provider_name)
    if fields is None:
        raise ValueError(f"No setup configuration for provider: {provider_name}")

    validator = _VALIDATORS.get(provider_name)
    if validator is None:
        raise ValueError(f"No validator implemented for provider: {provider_name}")
    return validator(credentials, fields)


def remove_credentials(provider_name: str) -> str:
    """Remove all stored credentials for a provider.

    Args:
        provider_name: The provider name.

    Returns:
        Success message string.

    Raises:
        ValueError: If the provider is unknown.
    """
    fields = PROVIDER_CREDENTIAL_MAP.get(provider_name)
    if fields is None:
        raise ValueError(f"No setup configuration for provider: {provider_name}")

    removed = []
    for field_def in fields:
        key = field_def["store_key"]
        if delete_credential(key):
            sync_setting(key, "")
            logger.info("Removed credential %s for %s", key, provider_name)
            removed.append(key)
        else:
            logger.info("Credential %s not found in Keychain for %s", key, provider_name)

    if removed:
        return f"{provider_name} credentials removed"
    return f"No credentials were configured for {provider_name}"
