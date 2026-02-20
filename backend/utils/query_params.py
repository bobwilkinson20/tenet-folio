"""Shared query parameter parsing utilities."""

import uuid

from fastapi import HTTPException


def parse_account_ids(account_ids: str | None) -> list[str] | None:
    """Parse comma-separated account IDs string into a validated list.

    Args:
        account_ids: Comma-separated string of account UUIDs, or None.

    Returns:
        List of validated UUID strings, or None if input is empty.

    Raises:
        HTTPException: If any ID is not a valid UUID.
    """
    if not account_ids:
        return None
    result = []
    for aid in account_ids.split(","):
        aid = aid.strip()
        if not aid:
            continue
        try:
            uuid.UUID(aid)
            result.append(aid)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid account ID format: {aid}",
            )
    return result if result else None
