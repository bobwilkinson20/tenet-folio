"""Provider setup service for in-app credential configuration.

Maps each provider to its required credential fields, validates credentials
server-side (e.g., exchanging a SimpleFIN setup token for an access URL),
and stores validated credentials in the macOS Keychain.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Callable, Literal, TypedDict

import httpx
from config import settings
from schemas.provider import ProviderCredentialInfo
from services.credential_manager import delete_credential, set_credential

logger = logging.getLogger(__name__)


@dataclass
class SetupResult:
    """Result of a provider setup validation."""

    message: str
    warnings: list[str] = field(default_factory=list)


def _sync_setting(store_key: str, value: str) -> None:
    """Update the in-memory settings singleton after a credential change.

    The ``settings`` object is loaded once at startup.  When credentials
    are added or removed via the setup service the keychain is updated but
    the singleton still holds the old value.  This helper patches the
    singleton so the provider registry sees the change immediately without
    requiring an app restart.
    """
    if hasattr(settings, store_key):
        setattr(settings, store_key, value)


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
    "IBKR": [
        {
            "key": "flex_token",
            "label": "Flex Token",
            "help_text": (
                "Your Flex Web Service token from IBKR Client Portal. "
                "Go to Settings > Flex Web Service Configuration to generate one."
            ),
            "input_type": "password",
            "store_key": "IBKR_FLEX_TOKEN",
        },
        {
            "key": "flex_query_id",
            "label": "Flex Query ID",
            "help_text": (
                "The numeric ID of your Flex Query. "
                "Find it under Reports > Flex Queries > Custom Flex Queries. "
                "The query must include Open Positions, Cash Report, and Trades sections."
            ),
            "input_type": "text",
            "store_key": "IBKR_FLEX_QUERY_ID",
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


def validate_and_store(provider_name: str, credentials: dict[str, str]) -> SetupResult:
    """Validate credentials and store them in Keychain.

    For SimpleFIN, this exchanges the setup token for an access URL
    before storing.

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
    for field_def in fields:
        key = field_def["store_key"]
        if delete_credential(key):
            _sync_setting(key, "")
            logger.info("Removed credential %s for %s", key, provider_name)
            removed.append(key)
        else:
            logger.info("Credential %s not found in Keychain for %s", key, provider_name)

    if removed:
        return f"{provider_name} credentials removed"
    return f"No credentials were configured for {provider_name}"


def _validate_simplefin(
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

    _sync_setting(store_key, access_url)
    logger.info("SimpleFIN credentials validated and stored")
    return SetupResult(
        message="SimpleFIN configured successfully. Access URL stored in Keychain."
    )


def _validate_ibkr(
    credentials: dict[str, str], fields: list[ProviderFieldDef]
) -> SetupResult:
    """Validate IBKR Flex credentials by downloading a test report.

    Downloads a Flex report to verify the token and query ID are valid,
    then checks that required sections and trade columns are present.
    """
    flex_token = credentials.get("flex_token", "").strip()
    if not flex_token:
        raise ValueError("Flex Token is required")

    flex_query_id = credentials.get("flex_query_id", "").strip()
    if not flex_query_id:
        raise ValueError("Flex Query ID is required")

    # Import ibflex and setup_ibkr validation helpers
    try:
        from ibflex import client as ibflex_client
    except ImportError as exc:
        raise RuntimeError(
            "ibflex library is not installed. "
            "Install it with: uv add ibflex"
        ) from exc

    from scripts.setup_ibkr import (
        REQUIRED_SECTION_COLUMNS,
        validate_query_sections,
        validate_trade_columns,
    )

    # Download a test Flex report to validate credentials.
    # The ibflex download function uses an internal polling loop with no
    # timeout parameter, so we wrap it in a thread with a timeout to prevent
    # the request handler from blocking indefinitely.  We avoid a `with`
    # block because its implicit shutdown(wait=True) would block until the
    # thread finishes — defeating the timeout.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(ibflex_client.download, flex_token, flex_query_id)
        data = future.result(timeout=60)
    except FuturesTimeoutError:
        executor.shutdown(wait=False)
        logger.warning("IBKR Flex download timed out after 60s")
        raise ValueError(
            "IBKR download timed out. The Flex Web Service may be slow or "
            "unresponsive. Please try again later."
        )
    except Exception as exc:
        executor.shutdown(wait=False)
        logger.warning("IBKR Flex credential validation failed: %s", exc)
        raise ValueError(
            "Failed to validate IBKR credentials. "
            "Check that your Flex Token and Query ID are correct. "
            "Common issues: expired token, invalid query ID, or IP restriction."
        ) from exc
    else:
        executor.shutdown(wait=False)

    # Check required sections
    missing_sections = validate_query_sections(data)
    if missing_sections:
        details = []
        for section in missing_sections:
            cols = REQUIRED_SECTION_COLUMNS.get(section)
            if cols:
                details.append(f"{section} (columns: {', '.join(cols)})")
            else:
                details.append(section)
        section_detail = "; ".join(details)
        raise ValueError(
            f"Flex Query is missing required sections: {section_detail}. "
            "Edit your query in IBKR Client Portal to add them."
        )

    # Check trade columns
    missing_required, missing_recommended = validate_trade_columns(data)
    if missing_required:
        col_list = ", ".join(missing_required)
        raise ValueError(
            f"Flex Query Trades section is missing required columns: {col_list}. "
            "Edit your query in IBKR Client Portal to add them."
        )

    # Collect warnings for missing recommended columns (non-blocking)
    warnings: list[str] = []
    if missing_recommended:
        col_list = ", ".join(missing_recommended)
        warnings.append(
            f"Trades section is missing recommended columns: {col_list}. "
            "Activities will sync but with incomplete data."
        )

    # Store both credentials
    for field_def in fields:
        key = field_def["key"]
        store_key = field_def["store_key"]
        value = credentials.get(key, "").strip()
        if not set_credential(store_key, value):
            raise RuntimeError(
                f"Failed to store {field_def['label']} in Keychain. "
                "Ensure keyring is installed and accessible."
            )
        _sync_setting(store_key, value)

    logger.info("IBKR Flex credentials validated and stored")
    return SetupResult(
        message="IBKR configured successfully. Credentials stored in Keychain.",
        warnings=warnings,
    )


# Dispatch table for provider-specific validators.
# Each validator receives (credentials, fields) and returns a SetupResult.
_VALIDATORS: dict[
    str, Callable[[dict[str, str], list[ProviderFieldDef]], SetupResult]
] = {
    "SimpleFIN": _validate_simplefin,
    "IBKR": _validate_ibkr,
}

if set(_VALIDATORS) != set(PROVIDER_CREDENTIAL_MAP):
    raise ValueError(
        f"PROVIDER_CREDENTIAL_MAP and _VALIDATORS are out of sync: "
        f"{set(PROVIDER_CREDENTIAL_MAP) - set(_VALIDATORS)} missing validators"
    )
