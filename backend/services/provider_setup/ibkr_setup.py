"""IBKR Flex provider setup — credential validation and storage."""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from .base import ProviderFieldDef, SetupResult, store_credentials

logger = logging.getLogger(__name__)

PROVIDER_NAME = "IBKR"

FIELDS: list[ProviderFieldDef] = [
    {
        "key": "flex_token",
        "label": "Flex Token",
        "help_text": (
            "Your Flex Web Service token from IBKR Client Portal. "
            "Go to Settings > Flex Web Service Configuration to generate one."
        ),
        "input_type": "password",
        "store_key": "IBKR_FLEX_TOKEN",
    },
    {
        "key": "flex_query_id",
        "label": "Flex Query ID",
        "help_text": (
            "The numeric ID of your Flex Query. "
            "Find it under Reports > Flex Queries > Custom Flex Queries. "
            "The query must include Open Positions, Cash Report, and Trades sections."
        ),
        "input_type": "text",
        "store_key": "IBKR_FLEX_QUERY_ID",
    },
]


def validate(
    credentials: dict[str, str], fields: list[ProviderFieldDef]
) -> SetupResult:
    """Validate IBKR Flex credentials by downloading a test report.

    Downloads a Flex report to verify the token and query ID are valid,
    then checks that required sections and trade columns are present.
    """
    flex_token = credentials.get("flex_token", "").strip()
    if not flex_token:
        raise ValueError("Flex Token is required")

    flex_query_id = credentials.get("flex_query_id", "").strip()
    if not flex_query_id:
        raise ValueError("Flex Query ID is required")

    # Import ibflex and setup_ibkr validation helpers
    try:
        from ibflex import client as ibflex_client
    except ImportError as exc:
        raise RuntimeError(
            "ibflex library is not installed. "
            "Install it with: uv add ibflex"
        ) from exc

    from scripts.setup_ibkr import (
        REQUIRED_SECTION_COLUMNS,
        validate_query_sections,
        validate_trade_columns,
    )

    # Download a test Flex report to validate credentials.
    # The ibflex download function uses an internal polling loop with no
    # timeout parameter, so we wrap it in a thread with a timeout to prevent
    # the request handler from blocking indefinitely.  We avoid a `with`
    # block because its implicit shutdown(wait=True) would block until the
    # thread finishes — defeating the timeout.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(ibflex_client.download, flex_token, flex_query_id)
        data = future.result(timeout=60)
    except FuturesTimeoutError:
        executor.shutdown(wait=False)
        logger.warning("IBKR Flex download timed out after 60s")
        raise ValueError(
            "IBKR download timed out. The Flex Web Service may be slow or "
            "unresponsive. Please try again later."
        )
    except Exception as exc:
        executor.shutdown(wait=False)
        logger.warning("IBKR Flex credential validation failed: %s", exc)
        raise ValueError(
            "Failed to validate IBKR credentials. "
            "Check that your Flex Token and Query ID are correct. "
            "Common issues: expired token, invalid query ID, or IP restriction."
        ) from exc
    else:
        executor.shutdown(wait=False)

    # Check required sections
    missing_sections = validate_query_sections(data)
    if missing_sections:
        details = []
        for section in missing_sections:
            cols = REQUIRED_SECTION_COLUMNS.get(section)
            if cols:
                details.append(f"{section} (columns: {', '.join(cols)})")
            else:
                details.append(section)
        section_detail = "; ".join(details)
        raise ValueError(
            f"Flex Query is missing required sections: {section_detail}. "
            "Edit your query in IBKR Client Portal to add them."
        )

    # Check trade columns
    missing_required, missing_recommended = validate_trade_columns(data)
    if missing_required:
        col_list = ", ".join(missing_required)
        raise ValueError(
            f"Flex Query Trades section is missing required columns: {col_list}. "
            "Edit your query in IBKR Client Portal to add them."
        )

    # Collect warnings for missing recommended columns (non-blocking)
    warnings: list[str] = []
    if missing_recommended:
        col_list = ", ".join(missing_recommended)
        warnings.append(
            f"Trades section is missing recommended columns: {col_list}. "
            "Activities will sync but with incomplete data."
        )

    # Store both credentials
    store_credentials(credentials, fields)

    logger.info("IBKR Flex credentials validated and stored")
    return SetupResult(
        message="IBKR configured successfully. Credentials stored in Keychain.",
        warnings=warnings,
    )
