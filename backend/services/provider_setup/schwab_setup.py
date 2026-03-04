"""Schwab provider setup — credential validation and storage."""

import logging

from .base import ProviderFieldDef, SetupResult, store_credentials

logger = logging.getLogger(__name__)

PROVIDER_NAME = "Schwab"

FIELDS: list[ProviderFieldDef] = [
    {
        "key": "app_key",
        "label": "App Key",
        "help_text": "Your Schwab App Key from the developer portal.",
        "input_type": "password",
        "store_key": "SCHWAB_APP_KEY",
    },
    {
        "key": "app_secret",
        "label": "App Secret",
        "help_text": "Your Schwab App Secret from the developer portal.",
        "input_type": "password",
        "store_key": "SCHWAB_APP_SECRET",
    },
    {
        "key": "callback_url",
        "label": "Callback URL",
        "help_text": (
            "OAuth callback URL — must match your Schwab app configuration exactly. "
            "Default: https://127.0.0.1:8000/api/schwab/callback"
        ),
        "input_type": "text",
        "store_key": "SCHWAB_CALLBACK_URL",
    },
]


def validate(
    credentials: dict[str, str], fields: list[ProviderFieldDef]
) -> SetupResult:
    """Validate Schwab app credentials and store in Keychain.

    Unlike other providers, Schwab cannot validate credentials in a
    single request.  This step stores the app key, secret, and callback
    URL, then prompts the user to complete OAuth authorization as a
    second step.
    """
    app_key = credentials.get("app_key", "").strip()
    if not app_key:
        raise ValueError("App Key is required")

    app_secret = credentials.get("app_secret", "").strip()
    if not app_secret:
        raise ValueError("App Secret is required")

    callback_url = credentials.get("callback_url", "").strip()
    if not callback_url:
        callback_url = "https://127.0.0.1:8000/api/schwab/callback"
        credentials = {**credentials, "callback_url": callback_url}

    if not callback_url.startswith("https://"):
        raise ValueError(
            "Callback URL must start with https://. "
            "Schwab requires HTTPS for OAuth callbacks."
        )

    # Verify schwab-py is installed and can generate an auth URL
    try:
        from schwab.auth import get_auth_context
    except ImportError as exc:
        raise RuntimeError(
            "schwab-py library is not installed. "
            "Install it with: uv add schwab-py"
        ) from exc

    try:
        get_auth_context(app_key, callback_url)
    except Exception as exc:
        raise ValueError(
            f"Failed to generate auth URL with provided credentials: {exc}"
        ) from exc

    store_credentials(credentials, fields)

    logger.info("Schwab credentials stored — OAuth authorization required next")
    return SetupResult(
        message=(
            "Schwab credentials saved. "
            "Complete the OAuth authorization step below to finish setup."
        )
    )
