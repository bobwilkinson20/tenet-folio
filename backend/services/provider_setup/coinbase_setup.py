"""Coinbase provider setup — credential validation and storage."""

import logging

from .base import ProviderFieldDef, SetupResult, store_credentials

logger = logging.getLogger(__name__)

PROVIDER_NAME = "Coinbase"

FIELDS: list[ProviderFieldDef] = [
    {
        "key": "api_key",
        "label": "API Key",
        "help_text": (
            "Your CDP API key from the Coinbase Developer Platform. "
            "Format: organizations/{org_id}/apiKeys/{key_id}"
        ),
        "input_type": "password",
        "store_key": "COINBASE_API_KEY",
    },
    {
        "key": "api_secret",
        "label": "API Secret",
        "help_text": (
            "Your ECDSA private key in PEM format. "
            "IMPORTANT: The key must use ECDSA algorithm — "
            "select it under Advanced Settings when creating the key. "
            "The default Ed25519 is not compatible."
        ),
        "input_type": "textarea",
        "store_key": "COINBASE_API_SECRET",
    },
]


def _normalize_pem(secret: str) -> str:
    """Normalize a PEM key string for storage.

    Converts literal ``\\n`` sequences (common copy-paste artifact from
    .env files or web UIs) to real newlines, normalizes Windows CRLF
    line endings, and strips surrounding whitespace.
    """
    return secret.replace("\\n", "\n").replace("\r\n", "\n").strip()


def validate(
    credentials: dict[str, str], fields: list[ProviderFieldDef]
) -> SetupResult:
    """Validate Coinbase CDP API credentials and store in Keychain.

    Tests the credentials by making a lightweight ``get_accounts(limit=1)``
    call, then stores them via the shared ``store_credentials()`` helper.
    """
    api_key = credentials.get("api_key", "").strip()
    if not api_key:
        raise ValueError("API Key is required")

    api_secret = credentials.get("api_secret", "").strip()
    if not api_secret:
        raise ValueError("API Secret is required")

    # Normalize PEM before validation and storage
    api_secret = _normalize_pem(api_secret)

    # Inline import: coinbase SDK is an optional dependency
    try:
        from coinbase.rest import RESTClient
    except ImportError as exc:
        raise RuntimeError(
            "Coinbase SDK is not installed. "
            "Install it with: uv add coinbase-advanced-py"
        ) from exc

    try:
        client = RESTClient(api_key=api_key, api_secret=api_secret)
        client.get_accounts(limit=1)
    except Exception as exc:
        error_msg = str(exc).lower()
        # The Coinbase SDK raises "Could not deserialize key data" when
        # an Ed25519 PEM is passed (via cryptography lib's load_pem_private_key).
        if "ed25519" in error_msg or "deserialize" in error_msg:
            raise ValueError(
                "Authentication failed: your API key appears to use Ed25519. "
                "Coinbase Advanced Trade requires ECDSA keys. "
                "Recreate the key and select ECDSA in Advanced Settings."
            ) from exc
        if "unauthorized" in error_msg or "401" in error_msg:
            raise ValueError(
                "Authentication failed: invalid API key or secret. "
                "Check that your credentials are correct and have not been revoked."
            ) from exc
        if "invalid api key" in error_msg or "invalid key" in error_msg:
            raise ValueError(
                "Invalid credential format. "
                "The API key should be in the format organizations/{org_id}/apiKeys/{key_id} "
                "and the secret should be an ECDSA PEM private key."
            ) from exc
        raise ValueError(
            f"Failed to validate Coinbase credentials: {exc}"
        ) from exc

    # Update credentials dict with normalized PEM before storage
    credentials = {**credentials, "api_secret": api_secret}
    store_credentials(credentials, fields)

    logger.info("Coinbase credentials validated and stored")
    return SetupResult(
        message="Coinbase configured successfully. Credentials stored in Keychain."
    )
