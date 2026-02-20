"""Pydantic schemas for user preferences."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PreferenceSet(BaseModel):
    """Request body for setting a preference value."""

    value: Any


class PreferenceResponse(BaseModel):
    """Response schema for a single preference with metadata."""

    key: str
    value: Any
    updated_at: datetime

    model_config = {"from_attributes": True}
