"""Shared utilities for ORM models."""

import uuid


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())
