"""Provider service - manages provider settings and status."""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from integrations.provider_registry import ALL_PROVIDER_NAMES, ProviderRegistry  # noqa: F401 (re-exported)
from models import Account
from models.provider_setting import ProviderSetting
from schemas.provider import ProviderStatusResponse

logger = logging.getLogger(__name__)


class ProviderService:
    """Service for managing provider settings and status."""

    @staticmethod
    def list_providers(
        db: Session, registry: Optional[ProviderRegistry] = None
    ) -> list[ProviderStatusResponse]:
        """List all known providers with their status.

        Args:
            db: Database session
            registry: Optional provider registry to check credentials.
                      If None, has_credentials will be False for all.

        Returns:
            List of ProviderStatusResponse for all known providers
        """
        # Load all provider settings in one query
        settings_map: dict[str, ProviderSetting] = {}
        for setting in db.query(ProviderSetting).all():
            settings_map[setting.provider_name] = setting

        # Load account counts and last sync times per provider
        account_stats = (
            db.query(
                Account.provider_name,
                func.count(Account.id),
                func.max(Account.last_sync_time),
            )
            .filter(Account.is_active.is_(True))
            .group_by(Account.provider_name)
            .all()
        )
        count_map: dict[str, int] = {}
        sync_map: dict[str, Optional[datetime]] = {}
        for provider_name, count, last_sync in account_stats:
            count_map[provider_name] = count
            sync_map[provider_name] = last_sync

        result = []
        for name in ALL_PROVIDER_NAMES:
            setting = settings_map.get(name)
            has_credentials = registry.is_configured(name) if registry else False
            is_enabled = setting.is_enabled if setting else True  # No row = enabled

            result.append(
                ProviderStatusResponse(
                    name=name,
                    has_credentials=has_credentials,
                    is_enabled=is_enabled,
                    account_count=count_map.get(name, 0),
                    last_sync_time=sync_map.get(name),
                )
            )

        return result

    @staticmethod
    def set_enabled(db: Session, provider_name: str, is_enabled: bool) -> None:
        """Enable or disable a provider.

        Args:
            db: Database session
            provider_name: Name of the provider
            is_enabled: Whether to enable or disable

        Raises:
            ValueError: If provider_name is not a known provider
        """
        if provider_name not in ALL_PROVIDER_NAMES:
            raise ValueError(f"Unknown provider: {provider_name}")

        setting = (
            db.query(ProviderSetting)
            .filter_by(provider_name=provider_name)
            .first()
        )
        if setting:
            setting.is_enabled = is_enabled
        else:
            setting = ProviderSetting(
                provider_name=provider_name, is_enabled=is_enabled
            )
            db.add(setting)

        db.commit()
        logger.info("Provider %s %s", provider_name, "enabled" if is_enabled else "disabled")

    @staticmethod
    def is_provider_enabled(db: Session, provider_name: str) -> bool:
        """Check if a provider is enabled.

        Returns True if no row exists (backwards compatible — all providers
        are enabled by default).

        Args:
            db: Database session
            provider_name: Name of the provider

        Returns:
            True if the provider is enabled or has no setting row
        """
        setting = (
            db.query(ProviderSetting)
            .filter_by(provider_name=provider_name)
            .first()
        )
        if setting is None:
            return True
        return setting.is_enabled
