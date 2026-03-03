"""Shared types and helpers for provider setup modules."""

import logging
from dataclasses import dataclass, field
from typing import Literal, TypedDict

from config import settings
from services.credential_manager import set_credential

logger = logging.getLogger(__name__)


@dataclass
class SetupResult:
    """Result of a provider setup validation."""

    message: str
    warnings: list[str] = field(default_factory=list)


class ProviderFieldDef(TypedDict, total=False):
    """Type-safe definition for a provider credential field."""

    key: str  # type: ignore[assignment]  # required
    label: str  # type: ignore[assignment]  # required
    help_text: str  # type: ignore[assignment]  # required
    input_type: Literal["text", "textarea", "password", "select"]  # type: ignore[assignment]  # required
    store_key: str  # type: ignore[assignment]  # required
    options: list[dict[str, str]]  # optional — for "select" fields


def sync_setting(store_key: str, value: str) -> None:
    """Update the in-memory settings singleton after a credential change.

    The ``settings`` object is loaded once at startup.  When credentials
    are added or removed via the setup service the keychain is updated but
    the singleton still holds the old value.  This helper patches the
    singleton so the provider registry sees the change immediately without
    requiring an app restart.
    """
    if hasattr(settings, store_key):
        setattr(settings, store_key, value)


def store_credentials(
    credentials: dict[str, str], fields: list[ProviderFieldDef]
) -> None:
    """Store all credential fields in Keychain and sync settings.

    Iterates over each field definition, looks up the user-supplied value
    from *credentials*, stores it via ``set_credential()``, and patches
    the in-memory settings singleton.

    Args:
        credentials: Dict of field key → value from the setup form.
        fields: Provider field definitions with store_key mappings.

    Raises:
        RuntimeError: If any credential fails to store.
    """
    for field_def in fields:
        key = field_def["key"]
        store_key = field_def["store_key"]
        value = credentials.get(key, "").strip()
        if not set_credential(store_key, value):
            raise RuntimeError(
                f"Failed to store {field_def['label']} in Keychain. "
                "Ensure keyring is installed and accessible."
            )
        sync_setting(store_key, value)
