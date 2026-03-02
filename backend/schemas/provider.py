"""Pydantic schemas for provider settings."""

from datetime import datetime
from typing import Literal, Optional

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


class ProviderSetupRequest(BaseModel):
    """Request body for provider setup. Credentials vary by provider."""

    credentials: dict[str, str]


class ProviderSetupResponse(BaseModel):
    """Response after successful provider setup."""

    provider: str
    message: str


class ProviderCredentialInfo(BaseModel):
    """Describes a credential field for a provider's setup form."""

    key: str
    label: str
    help_text: str = ""
    input_type: Literal["text", "textarea", "password"] = "text"
