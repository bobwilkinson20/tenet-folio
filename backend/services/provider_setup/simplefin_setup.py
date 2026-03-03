"""SimpleFIN provider setup — token exchange and credential storage."""

import logging

import httpx
from services.credential_manager import set_credential

from .base import ProviderFieldDef, SetupResult, sync_setting

logger = logging.getLogger(__name__)

PROVIDER_NAME = "SimpleFIN"

FIELDS: list[ProviderFieldDef] = [
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
]


def validate(
    credentials: dict[str, str], fields: list[ProviderFieldDef]
) -> SetupResult:
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

    # Look up store_key from fields param.
    store_key_field = next((f for f in fields if f["key"] == "setup_token"), None)
    if store_key_field is None:
        raise ValueError("No field definition found for setup_token")
    store_key = store_key_field["store_key"]

    if not set_credential(store_key, access_url):
        raise RuntimeError(
            "Failed to store credentials in Keychain. "
            "Ensure keyring is installed and accessible."
        )

    sync_setting(store_key, access_url)
    logger.info("SimpleFIN credentials validated and stored")
    return SetupResult(
        message="SimpleFIN configured successfully. Access URL stored in Keychain."
    )
