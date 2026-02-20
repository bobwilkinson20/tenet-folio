"""Service for managing Security records."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from models import Security

logger = logging.getLogger(__name__)


class SecurityService:
    """Centralized operations on the Security master list."""

    @staticmethod
    def ensure_exists(
        db: Session,
        ticker: str,
        name: Optional[str] = None,
        update_name: bool = False,
    ) -> Security:
        """Ensure a Security record exists for the given ticker.

        Creates the record if it doesn't exist.  When the record already
        exists the ``name`` field is updated only when:
        - ``update_name=False`` (default): name is set if the existing
          record has no name (i.e. ``security.name`` is falsy).
        - ``update_name=True``: name is always overwritten with the
          supplied value.

        Args:
            db: Database session
            ticker: The security ticker symbol
            name: Optional security name
            update_name: If True, overwrite existing name unconditionally

        Returns:
            The Security record (flushed but not committed)
        """
        security = db.query(Security).filter_by(ticker=ticker).first()

        if not security:
            security = Security(ticker=ticker, name=name or ticker)
            db.add(security)
            db.flush()
            logger.info("Created security: %s", ticker)
        elif name and update_name:
            security.name = name
            db.flush()
            logger.info("Updated security name: %s -> %s", ticker, name)
        elif name and not security.name:
            security.name = name
            db.flush()
            logger.info("Filled missing security name: %s -> %s", ticker, name)

        return security
