"""Provider settings API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from integrations.provider_registry import ProviderRegistry, get_provider_registry
from schemas.provider import (
    ProviderCredentialInfo,
    ProviderSetupRequest,
    ProviderSetupResponse,
    ProviderStatusResponse,
    ProviderUpdateRequest,
)
from services.provider_service import ALL_PROVIDER_NAMES, ProviderService
from services import provider_setup_service
from services.provider_setup_service import PROVIDER_CREDENTIAL_MAP

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


@router.get("/{name}/setup-info", response_model=list[ProviderCredentialInfo])
def get_setup_info(name: str):
    """Return field definitions for the provider's setup form."""
    if name not in ALL_PROVIDER_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    if name not in PROVIDER_CREDENTIAL_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"No setup configuration for provider: {name}",
        )

    return provider_setup_service.get_setup_fields(name)


@router.post("/{name}/setup", response_model=ProviderSetupResponse)
def setup_provider(name: str, body: ProviderSetupRequest):
    """Validate credentials and store in Keychain."""
    if name not in ALL_PROVIDER_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    if name not in PROVIDER_CREDENTIAL_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"No setup configuration for provider: {name}",
        )

    try:
        message = provider_setup_service.validate_and_store(name, body.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("Provider %s configured via in-app setup", name)
    return ProviderSetupResponse(provider=name, message=message)


@router.delete("/{name}/credentials", response_model=ProviderSetupResponse)
def remove_credentials(name: str):
    """Remove all credentials for a provider from Keychain."""
    if name not in ALL_PROVIDER_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    if name not in PROVIDER_CREDENTIAL_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"No setup configuration for provider: {name}",
        )

    message = provider_setup_service.remove_credentials(name)
    logger.info("Provider %s credentials removed via in-app setup", name)
    return ProviderSetupResponse(provider=name, message=message)
