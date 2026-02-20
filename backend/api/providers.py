"""Provider settings API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from integrations.provider_registry import ProviderRegistry, get_provider_registry
from schemas.provider import ProviderStatusResponse, ProviderUpdateRequest
from services.provider_service import ALL_PROVIDER_NAMES, ProviderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/providers", tags=["providers"])


def get_registry() -> ProviderRegistry:
    """Get the provider registry (dependency for injection in tests)."""
    return get_provider_registry()


@router.get("", response_model=list[ProviderStatusResponse])
def list_providers(
    db: Session = Depends(get_db),
    registry: ProviderRegistry = Depends(get_registry),
):
    """List all known providers with their configuration and enabled status."""
    return ProviderService.list_providers(db, registry=registry)


@router.put("/{name}", response_model=ProviderStatusResponse)
def update_provider(
    name: str,
    body: ProviderUpdateRequest,
    db: Session = Depends(get_db),
    registry: ProviderRegistry = Depends(get_registry),
):
    """Enable or disable a provider."""
    if name not in ALL_PROVIDER_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")

    ProviderService.set_enabled(db, name, body.is_enabled)

    # Return the updated status for this single provider
    all_providers = ProviderService.list_providers(db, registry=registry)
    for p in all_providers:
        if p.name == name:
            return p

    raise HTTPException(status_code=404, detail=f"Provider not found: {name}")
