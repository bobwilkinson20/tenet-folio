"""SnapTrade provider setup — credential validation and storage."""

import logging

from services.credential_manager import get_credential, set_credential

from .base import ProviderFieldDef, SetupResult, store_credentials, sync_setting

logger = logging.getLogger(__name__)

PROVIDER_NAME = "SnapTrade"

_DEFAULT_USER_ID = "portfolio-user"

FIELDS: list[ProviderFieldDef] = [
    {
        "key": "client_id",
        "label": "Client ID",
        "help_text": "Your SnapTrade client ID from the partner dashboard.",
        "input_type": "password",
        "store_key": "SNAPTRADE_CLIENT_ID",
    },
    {
        "key": "consumer_key",
        "label": "Consumer Key",
        "help_text": "Your SnapTrade consumer key (API secret).",
        "input_type": "password",
        "store_key": "SNAPTRADE_CONSUMER_KEY",
    },
    {
        "key": "user_id",
        "label": "User ID (optional)",
        "help_text": (
            f'Defaults to "{_DEFAULT_USER_ID}". '
            "Change this if you registered with a different user ID "
            "(e.g., per-profile IDs like portfolio-paper). "
            "If reconnecting an existing user, also provide User Secret."
        ),
        "input_type": "text",
        "required": False,
        "store_key": "SNAPTRADE_USER_ID",
    },
    {
        "key": "user_secret",
        "label": "User Secret (optional)",
        "help_text": (
            "Leave blank for first-time setup. "
            "Only needed if you previously registered via the CLI script "
            "and want to preserve existing brokerage connections."
        ),
        "input_type": "password",
        "required": False,
        "store_key": "SNAPTRADE_USER_SECRET",
    },
]

# API credentials stored by store_credentials().  user_id and user_secret are
# handled separately since they may come from registration or Keychain.
_API_FIELDS: list[ProviderFieldDef] = [
    f for f in FIELDS if f["key"] in ("client_id", "consumer_key")
]


def _get_attr(obj: object, key: str, default: object = None) -> object:
    """Get attribute from dict or object (SDK responses vary)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _extract_user_secret(response: object) -> str:
    """Extract the userSecret from a SnapTrade registration response."""
    body = response.body if hasattr(response, "body") else response
    secret = _get_attr(body, "userSecret") or _get_attr(body, "user_secret")
    if not secret:
        raise ValueError(f"Unexpected response from SnapTrade: {body}")
    return str(secret)


def _validate_with_user_secret(
    client: object, user_id: str, user_secret: str
) -> None:
    """Validate API credentials against an existing SnapTrade user."""
    try:
        client.account_information.list_user_accounts(
            user_id=user_id,
            user_secret=user_secret,
        )
    except Exception as exc:
        error_msg = str(exc).lower()
        if any(s in error_msg for s in ("unauthorized", "403", "401", "404", "not found")):
            raise ValueError(
                "Invalid credentials: the Client ID / Consumer Key don't match "
                "the existing user, or the User Secret is incorrect."
            ) from exc
        raise ValueError(
            f"Failed to validate SnapTrade credentials: {exc}"
        ) from exc


def _register_user(client: object, user_id: str) -> str:
    """Register a new SnapTrade user. Returns the user secret."""
    try:
        response = client.authentication.register_snap_trade_user(
            user_id=user_id,
        )
        return _extract_user_secret(response)
    except ValueError:
        raise
    except Exception as exc:
        error_msg = str(exc).lower()

        if "unauthorized" in error_msg or "403" in error_msg or "401" in error_msg:
            raise ValueError(
                "Authentication failed: invalid Client ID or Consumer Key. "
                "Check your credentials on the SnapTrade partner dashboard."
            ) from exc

        if "already exist" in error_msg or "1010" in error_msg:
            raise ValueError(
                "A SnapTrade user already exists for these credentials. "
                "To preserve your existing brokerage connections, enter your "
                "User ID and User Secret (from your original setup) in the "
                "optional fields and try again."
            ) from exc

        raise ValueError(
            f"Failed to register SnapTrade user: {exc}"
        ) from exc


def _store_user_credentials(user_id: str, user_secret: str) -> None:
    """Store USER_ID and USER_SECRET in Keychain and sync settings.

    If this fails after a successful registration, the SnapTrade user exists
    but the app has no local record.  Recovery: re-run setup with the user_id
    and user_secret from the original registration in the optional fields.
    """
    if not set_credential("SNAPTRADE_USER_ID", user_id):
        raise RuntimeError("Failed to store SNAPTRADE_USER_ID in Keychain.")
    if not set_credential("SNAPTRADE_USER_SECRET", user_secret):
        raise RuntimeError("Failed to store SNAPTRADE_USER_SECRET in Keychain.")

    # Sync in-memory settings only after both writes succeed to avoid
    # a partial state where USER_ID is in memory but USER_SECRET is not.
    sync_setting("SNAPTRADE_USER_ID", user_id)
    sync_setting("SNAPTRADE_USER_SECRET", user_secret)


def validate(
    credentials: dict[str, str], fields: list[ProviderFieldDef]
) -> SetupResult:
    """Validate SnapTrade API credentials and store in Keychain.

    Three paths:
    1. USER_ID + USER_SECRET already in Keychain → revalidate with new API creds
    2. user_secret provided in form → validate and store everything
    3. Neither → register a new user (fails if user already exists on SnapTrade)
    """
    client_id = credentials.get("client_id", "").strip()
    if not client_id:
        raise ValueError("Client ID is required")

    consumer_key = credentials.get("consumer_key", "").strip()
    if not consumer_key:
        raise ValueError("Consumer Key is required")

    # Optional fields for existing users without local credentials
    form_user_id = credentials.get("user_id", "").strip()
    form_user_secret = credentials.get("user_secret", "").strip()

    # Inline import: snaptrade SDK is an optional dependency
    try:
        from snaptrade_client import SnapTrade
    except ImportError as exc:
        raise RuntimeError(
            "SnapTrade SDK is not installed. "
            "Install it with: uv add snaptrade-python-sdk"
        ) from exc

    client = SnapTrade(consumer_key=consumer_key, client_id=client_id)

    # Path 1: Existing user credentials in Keychain.
    # When Keychain already has USER_ID/USER_SECRET, we use those and ignore
    # any form-provided user_id/user_secret.  To change the stored user, the
    # user should first remove credentials via the UI, then re-setup.
    existing_user_id = get_credential("SNAPTRADE_USER_ID")
    existing_user_secret = get_credential("SNAPTRADE_USER_SECRET")

    if existing_user_id and existing_user_secret:
        _validate_with_user_secret(client, existing_user_id, existing_user_secret)
        store_credentials(credentials, _API_FIELDS)
        logger.info("SnapTrade credentials re-validated and stored (existing user)")
        return SetupResult(
            message="SnapTrade configured successfully. Existing user preserved."
        )

    # Path 2: User secret provided in form (existing user, no local creds).
    # Note: if store_credentials succeeds but _store_user_credentials fails,
    # the app will have API creds but no user creds.  Re-running setup with
    # the same form values will recover (Path 2 again).
    if form_user_secret:
        user_id = form_user_id or _DEFAULT_USER_ID
        _validate_with_user_secret(client, user_id, form_user_secret)
        store_credentials(credentials, _API_FIELDS)
        _store_user_credentials(user_id, form_user_secret)
        logger.info("SnapTrade credentials validated with provided user secret")
        return SetupResult(
            message=(
                "SnapTrade configured successfully. "
                "Existing user and connections preserved."
            )
        )

    # Path 3: Fresh registration
    user_id = form_user_id or _DEFAULT_USER_ID
    user_secret = _register_user(client, user_id)
    store_credentials(credentials, _API_FIELDS)
    _store_user_credentials(user_id, user_secret)
    logger.info("SnapTrade credentials validated and new user registered")
    return SetupResult(
        message="SnapTrade configured successfully. Credentials stored in Keychain."
    )
