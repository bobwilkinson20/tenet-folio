"""Provider setup service for in-app credential configuration.

Maps each provider to its required credential fields, validates credentials
server-side (e.g., exchanging a SimpleFIN setup token for an access URL),
and stores validated credentials in the macOS Keychain.
"""

import logging

from schemas.provider import ProviderCredentialInfo
from services.credential_manager import delete_credential, set_credential

logger = logging.getLogger(__name__)


# Maps provider name → list of credential field definitions.
# Each entry describes one input field in the setup form.
# "store_key" is the credential key stored in Keychain (may differ from "key").
PROVIDER_CREDENTIAL_MAP: dict[str, list[dict]] = {
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

# Maps provider name → list of Keychain keys to delete on removal.
PROVIDER_CREDENTIAL_KEYS: dict[str, list[str]] = {
    "SimpleFIN": ["SIMPLEFIN_ACCESS_URL"],
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
            help_text=f.get("help_text", ""),
            input_type=f.get("input_type", "text"),
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
    if provider_name == "SimpleFIN":
        return _validate_simplefin(credentials, fields)

    raise ValueError(f"No validator implemented for provider: {provider_name}")


def remove_credentials(provider_name: str) -> str:
    """Remove all stored credentials for a provider.

    Args:
        provider_name: The provider name.

    Returns:
        Success message string.

    Raises:
        ValueError: If the provider is unknown.
    """
    keys = PROVIDER_CREDENTIAL_KEYS.get(provider_name)
    if keys is None:
        raise ValueError(f"No credential keys for provider: {provider_name}")

    for key in keys:
        delete_credential(key)
        logger.info("Removed credential %s for %s", key, provider_name)

    return f"{provider_name} credentials removed"


def _validate_simplefin(
    credentials: dict[str, str], fields: list[dict]
) -> str:
    """Validate SimpleFIN setup token and store access URL.

    Exchanges the one-time setup token for a permanent access URL
    using the simplefin library, then stores it in Keychain.
    """
    setup_token = credentials.get("setup_token", "").strip()
    if not setup_token:
        raise ValueError("Setup token is required")

    # Exchange token for access URL using the simplefin library
    from simplefin import SimpleFINClient as SimpleFINLibClient

    try:
        access_url = SimpleFINLibClient.get_access_url(setup_token)
    except Exception as exc:
        raise ValueError(
            f"Failed to exchange setup token: {exc}. "
            "The token may have already been used (tokens are single-use) "
            "or is invalid."
        ) from exc

    # Store the access URL
    store_key = fields[0]["store_key"]
    if not set_credential(store_key, access_url):
        raise RuntimeError(
            "Failed to store credentials in Keychain. "
            "Ensure keyring is installed and accessible."
        )

    logger.info("SimpleFIN credentials validated and stored")
    return "SimpleFIN configured successfully. Access URL stored in Keychain."
