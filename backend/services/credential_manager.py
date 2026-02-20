"""Keyring-backed credential storage for provider secrets.

Provides a thin wrapper around the ``keyring`` library to store and
retrieve provider credentials in the macOS Keychain (or any other
backend supported by keyring).  The ``keyring`` import is lazy so the
rest of the app works even if keyring is not installed.
"""

import logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "tenet-folio"

CREDENTIAL_KEYS: frozenset[str] = frozenset(
    {
        "SNAPTRADE_CLIENT_ID",
        "SNAPTRADE_CONSUMER_KEY",
        "SNAPTRADE_USER_ID",
        "SNAPTRADE_USER_SECRET",
        "SIMPLEFIN_ACCESS_URL",
        "IBKR_FLEX_TOKEN",
        "IBKR_FLEX_QUERY_ID",
        "COINBASE_API_KEY",
        "COINBASE_API_SECRET",
        "SCHWAB_APP_KEY",
        "SCHWAB_APP_SECRET",
        "SCHWAB_CALLBACK_URL",
        "SQLCIPHER_KEY",
    }
)


def get_credential(key: str) -> str | None:
    """Retrieve a credential from the keychain.

    Args:
        key: The credential name (e.g. ``"SNAPTRADE_CLIENT_ID"``).

    Returns:
        The credential value, or ``None`` if not found or keyring
        is unavailable.
    """
    try:
        import keyring
    except ImportError:
        return None

    try:
        return keyring.get_password(SERVICE_NAME, key)
    except Exception:
        logger.debug("keyring lookup failed for %s", key, exc_info=True)
        return None


def set_credential(key: str, value: str) -> bool:
    """Store a credential in the keychain.

    Only keys listed in :data:`CREDENTIAL_KEYS` are accepted.

    Args:
        key: The credential name (must be in ``CREDENTIAL_KEYS``).
        value: The credential value (must be non-empty).

    Returns:
        ``True`` if stored successfully, ``False`` otherwise.
    """
    if key not in CREDENTIAL_KEYS:
        logger.warning("Attempted to store non-credential key: %s", key)
        return False
    if not value or not value.strip():
        logger.warning("Attempted to store empty value for %s", key)
        return False

    try:
        import keyring
    except ImportError:
        logger.warning("keyring is not installed — cannot store credentials")
        return False

    try:
        keyring.set_password(SERVICE_NAME, key, value)
        logger.info("Stored %s in keychain", key)
        return True
    except Exception:
        logger.warning("Failed to store %s in keychain", key, exc_info=True)
        return False


def delete_credential(key: str) -> bool:
    """Remove a credential from the keychain.

    Only keys listed in :data:`CREDENTIAL_KEYS` are accepted.

    Args:
        key: The credential name (must be in ``CREDENTIAL_KEYS``).

    Returns:
        ``True`` if deleted successfully, ``False`` otherwise.
    """
    if key not in CREDENTIAL_KEYS:
        logger.warning("Attempted to delete non-credential key: %s", key)
        return False

    try:
        import keyring
    except ImportError:
        return False

    try:
        keyring.delete_password(SERVICE_NAME, key)
        logger.info("Deleted %s from keychain", key)
        return True
    except Exception:
        logger.debug("Failed to delete %s from keychain", key, exc_info=True)
        return False


def list_credentials() -> dict[str, str]:
    """Return all credentials stored in the keychain.

    Checks each key in :data:`CREDENTIAL_KEYS` and returns those that
    have a non-``None`` value.

    Returns:
        Dict mapping credential names to their values.
    """
    result: dict[str, str] = {}
    for key in sorted(CREDENTIAL_KEYS):
        value = get_credential(key)
        if value is not None:
            result[key] = value
    return result
