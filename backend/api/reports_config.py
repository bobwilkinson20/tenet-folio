"""Reports configuration API — credentials, report types, and sheet targets."""

import json
import logging
from typing import Optional

import gspread
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models.report_sheet_target import ReportSheetTarget
from schemas.report import (
    GoogleSheetsCredentialSetRequest,
    GoogleSheetsCredentialStatus,
    ReportSheetTargetCreateRequest,
    ReportSheetTargetResponse,
    ReportSheetTargetUpdateRequest,
    ReportTypeResponse,
)
from services.credential_manager import delete_credential, set_credential
from services.google_sheets_service import (
    GoogleSheetsError,
    validate_spreadsheet_access,
    validate_template_tab,
)
from services.report_types import get_report_type, list_report_types

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports/config", tags=["reports-config"])


# ---------------------------------------------------------------------------
# Google Sheets Credentials
# ---------------------------------------------------------------------------


@router.get("/credentials", response_model=GoogleSheetsCredentialStatus)
def get_credential_status():
    """Return whether Google Sheets credentials are configured."""
    creds_json = settings.GOOGLE_SHEETS_CREDENTIALS
    if not creds_json:
        return GoogleSheetsCredentialStatus(configured=False)

    try:
        data = json.loads(creds_json)
        email = data.get("client_email")
    except (json.JSONDecodeError, AttributeError):
        return GoogleSheetsCredentialStatus(configured=True)

    return GoogleSheetsCredentialStatus(configured=True, service_account_email=email)


@router.post("/credentials", response_model=GoogleSheetsCredentialStatus)
def set_credentials(body: GoogleSheetsCredentialSetRequest):
    """Validate and store Google Sheets service account credentials."""
    raw = body.credentials_json.strip()

    # Validate JSON structure
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Credentials must be a JSON object.")

    for field in ("client_email", "private_key"):
        if field not in data:
            raise HTTPException(
                status_code=400,
                detail=f"Credentials JSON missing required field: '{field}'.",
            )

    # Validate authentication by creating a gspread client
    try:
        gspread.service_account_from_dict(data)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Credentials authentication failed: {e}",
        )

    # Store in keychain
    if not set_credential("GOOGLE_SHEETS_CREDENTIALS", raw):
        raise HTTPException(
            status_code=500,
            detail="Failed to store credentials in keychain.",
        )

    # Sync in-memory settings
    settings.GOOGLE_SHEETS_CREDENTIALS = raw

    logger.info("Google Sheets credentials configured for %s", data["client_email"])

    return GoogleSheetsCredentialStatus(
        configured=True,
        service_account_email=data["client_email"],
    )


@router.delete("/credentials", status_code=204)
def remove_credentials():
    """Remove Google Sheets credentials from keychain."""
    delete_credential("GOOGLE_SHEETS_CREDENTIALS")
    settings.GOOGLE_SHEETS_CREDENTIALS = ""
    logger.info("Google Sheets credentials removed")


# ---------------------------------------------------------------------------
# Report Types
# ---------------------------------------------------------------------------


@router.get("/types", response_model=list[ReportTypeResponse])
def get_types():
    """List all registered report types."""
    return [
        ReportTypeResponse(
            id=rt.id,
            display_name=rt.display_name,
            description=rt.description,
            config_fields=rt.config_fields,
        )
        for rt in list_report_types()
    ]


# ---------------------------------------------------------------------------
# Sheet Targets
# ---------------------------------------------------------------------------


def _target_to_response(target: ReportSheetTarget) -> ReportSheetTargetResponse:
    """Convert a ReportSheetTarget model to a response schema."""
    return ReportSheetTargetResponse(
        id=target.id,
        report_type=target.report_type,
        spreadsheet_id=target.spreadsheet_id,
        display_name=target.display_name,
        config=target.config_dict,
        created_at=target.created_at,
        updated_at=target.updated_at,
    )


@router.get("/targets", response_model=list[ReportSheetTargetResponse])
def list_targets(
    report_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List all sheet targets, optionally filtered by report type."""
    query = db.query(ReportSheetTarget)
    if report_type:
        query = query.filter(ReportSheetTarget.report_type == report_type)
    targets = query.order_by(ReportSheetTarget.created_at).all()
    return [_target_to_response(t) for t in targets]


@router.post("/targets", response_model=ReportSheetTargetResponse, status_code=201)
def create_target(
    body: ReportSheetTargetCreateRequest,
    db: Session = Depends(get_db),
):
    """Create a new sheet target with validation."""
    # Validate report type
    rt = get_report_type(body.report_type)
    if rt is None:
        raise HTTPException(status_code=400, detail=f"Unknown report type: '{body.report_type}'.")

    # Validate credentials configured
    if not settings.GOOGLE_SHEETS_CREDENTIALS:
        raise HTTPException(
            status_code=400,
            detail="Google Sheets credentials are not configured. Add them first.",
        )

    # Validate spreadsheet access
    try:
        sheet_title = validate_spreadsheet_access(body.spreadsheet_id)
    except GoogleSheetsError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Validate type-specific config
    config = body.config.copy()

    # Apply defaults for missing config fields
    for cf in rt.config_fields:
        if cf["key"] not in config and cf.get("default") is not None:
            config[cf["key"]] = cf["default"]

    # Check required fields
    for cf in rt.config_fields:
        if cf.get("required") and not config.get(cf["key"]):
            raise HTTPException(
                status_code=400,
                detail=f"Missing required config field: '{cf['key']}'.",
            )

    # Validate template tab if present
    if "template_tab" in config:
        try:
            validate_template_tab(body.spreadsheet_id, config["template_tab"])
        except GoogleSheetsError as e:
            raise HTTPException(status_code=400, detail=str(e))

    display_name = body.display_name or sheet_title

    target = ReportSheetTarget(
        report_type=body.report_type,
        spreadsheet_id=body.spreadsheet_id,
        display_name=display_name,
    )
    target.config_dict = config

    db.add(target)
    db.commit()
    db.refresh(target)

    logger.info("Created sheet target '%s' for report type '%s'", display_name, body.report_type)

    return _target_to_response(target)


@router.put("/targets/{target_id}", response_model=ReportSheetTargetResponse)
def update_target(
    target_id: str,
    body: ReportSheetTargetUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update an existing sheet target."""
    target = db.query(ReportSheetTarget).filter(ReportSheetTarget.id == target_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Sheet target not found.")

    if body.display_name is not None:
        target.display_name = body.display_name

    if body.config is not None:
        # Re-validate config if changed
        rt = get_report_type(target.report_type)
        if rt:
            for cf in rt.config_fields:
                if cf.get("required") and not body.config.get(cf["key"]):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Missing required config field: '{cf['key']}'.",
                    )

            # Validate template tab if present and changed
            if "template_tab" in body.config:
                try:
                    validate_template_tab(target.spreadsheet_id, body.config["template_tab"])
                except GoogleSheetsError as e:
                    raise HTTPException(status_code=400, detail=str(e))

        target.config_dict = body.config

    db.commit()
    db.refresh(target)

    logger.info("Updated sheet target '%s'", target.display_name)

    return _target_to_response(target)


@router.delete("/targets/{target_id}", status_code=204)
def delete_target(
    target_id: str,
    db: Session = Depends(get_db),
):
    """Delete a sheet target."""
    target = db.query(ReportSheetTarget).filter(ReportSheetTarget.id == target_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Sheet target not found.")

    logger.info("Deleted sheet target '%s'", target.display_name)

    db.delete(target)
    db.commit()
