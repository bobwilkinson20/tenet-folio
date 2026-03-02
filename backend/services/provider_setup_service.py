"""Provider setup service for in-app credential configuration.

Maps each provider to its required credential fields, validates credentials
server-side (e.g., exchanging a SimpleFIN setup token for an access URL),
and stores validated credentials in the macOS Keychain.
"""

import logging
from typing import Callable, Literal, TypedDict

import httpx
from schemas.provider import ProviderCredentialInfo
from services.credential_manager import delete_credential, set_credential

logger = logging.getLogger(__name__)


class ProviderFieldDef(TypedDict):
    """Type-safe definition for a provider credential field."""

    key: str
    label: str
    help_text: str
    input_type: Literal["text", "textarea", "password"]
    store_key: str


# Maps provider name → list of credential field definitions.
# Each entry describes one input field in the setup form.
# "store_key" is the credential key stored in Keychain (may differ from "key").
PROVIDER_CREDENTIAL_MAP: dict[str, list[ProviderFieldDef]] = {
    "SimpleFIN": [
        {
            "key": "setup_token",
            "label": "Setup Token",
            "help_text": (
                "Paste the setup token from SimpleFIN Bridge. "
                "Go to beta-bridge.simplefin.org, create a connection, "
                "and copy the base64 token. It will be exchanged for a "
                "permanent access URL."
            ),
            "input_type": "password",
            "store_key": "SIMPLEFIN_ACCESS_URL",
        },
    ],
}


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


def validate_and_store(provider_name: str, credentials: dict[str, str]) -> str:
    """Validate credentials and store them in Keychain.

    For SimpleFIN, this exchanges the setup token for an access URL
    before storing.

    Args:
        provider_name: The provider name.
        credentials: Dict of field key → value from the setup form.

    Returns:
        Success message string.

    Raises:
        ValueError: If the provider is unknown or credentials are invalid.
        RuntimeError: If credential storage fails.
    """
    fields = PROVIDER_CREDENTIAL_MAP.get(provider_name)
    if fields is None:
        raise ValueError(f"No setup configuration for provider: {provider_name}")

    # Dispatch to provider-specific validation
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
    for field in fields:
        key = field["store_key"]
        if delete_credential(key):
            logger.info("Removed credential %s for %s", key, provider_name)
            removed.append(key)
        else:
            logger.info("Credential %s not found in Keychain for %s", key, provider_name)

    if removed:
        return f"{provider_name} credentials removed"
    return f"No credentials were configured for {provider_name}"


def _validate_simplefin(
    credentials: dict[str, str], fields: list[ProviderFieldDef]
) -> str:
    """Validate SimpleFIN setup token and store access URL.

    Exchanges the one-time setup token for a permanent access URL
    using the simplefin library, then stores it in Keychain.
    """
    setup_token = credentials.get("setup_token", "").strip()
    if not setup_token:
        raise ValueError("Setup token is required")

    # Inline import: simplefin is an optional dependency that may not be
    # installed in all environments (e.g., test, CI without extras).
    try:
        from simplefin import SimpleFINClient as SimpleFINLibClient
    except ImportError as exc:
        raise RuntimeError(
            "SimpleFIN library is not installed. "
            "Install it with: uv add simplefin"
        ) from exc

    try:
        access_url = SimpleFINLibClient.get_access_url(setup_token)
    except (ValueError, UnicodeDecodeError) as exc:
        logger.warning("SimpleFIN token exchange failed (bad token format): %s", exc)
        raise ValueError(
            "Failed to exchange setup token: invalid format. "
            "The token should be a base64 string from the SimpleFIN Bridge."
        ) from exc
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning("SimpleFIN token exchange failed (network): %s", exc)
        raise ValueError(
            f"Failed to exchange setup token: could not reach SimpleFIN ({exc}). "
            "Check your network connection and try again."
        ) from exc
    except Exception as exc:
        logger.warning("SimpleFIN token exchange failed: %s", exc)
        raise ValueError(
            "Failed to exchange setup token. "
            "The token may have already been used (tokens are single-use) "
            "or is invalid."
        ) from exc

    # Look up store_key from PROVIDER_CREDENTIAL_MAP via fields param.
    # Uses next() rather than fields[0] so this pattern generalizes to
    # multi-field providers where validators need a specific field by key.
    store_key_field = next((f for f in fields if f["key"] == "setup_token"), None)
    if store_key_field is None:
        raise ValueError("No field definition found for setup_token")
    store_key = store_key_field["store_key"]

    if not set_credential(store_key, access_url):
        raise RuntimeError(
            "Failed to store credentials in Keychain. "
            "Ensure keyring is installed and accessible."
        )

    logger.info("SimpleFIN credentials validated and stored")
    return "SimpleFIN configured successfully. Access URL stored in Keychain."


# Dispatch table for provider-specific validators.
# Each validator receives (credentials, fields) and returns a success message.
_VALIDATORS: dict[str, Callable[[dict[str, str], list[ProviderFieldDef]], str]] = {
    "SimpleFIN": _validate_simplefin,
}

if set(_VALIDATORS) != set(PROVIDER_CREDENTIAL_MAP):
    raise ValueError(
        f"PROVIDER_CREDENTIAL_MAP and _VALIDATORS are out of sync: "
        f"{set(PROVIDER_CREDENTIAL_MAP) - set(_VALIDATORS)} missing validators"
    )
