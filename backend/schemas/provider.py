"""Pydantic schemas for provider settings."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProviderStatusResponse(BaseModel):
    """Response schema for a single provider's status."""

    name: str
    has_credentials: bool
    is_enabled: bool
    account_count: int
    last_sync_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProviderUpdateRequest(BaseModel):
    """Request body for updating provider settings."""

    is_enabled: bool
