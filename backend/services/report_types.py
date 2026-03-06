"""Registry of available report types and their configuration."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReportTypeConfig:
    """Describes a report type and its configurable fields."""

    id: str
    display_name: str
    description: str
    config_fields: list[dict] = field(default_factory=list)


REPORT_TYPES: dict[str, ReportTypeConfig] = {
    "account_allocation": ReportTypeConfig(
        id="account_allocation",
        display_name="Account Allocation",
        description="Portfolio allocation report broken down by account and asset class.",
        config_fields=[
            {
                "key": "template_tab",
                "label": "Template Tab",
                "help_text": "Name of the template tab to duplicate for each report.",
                "required": True,
                "default": "Template",
            },
        ],
    ),
}


def get_report_type(report_type_id: str) -> ReportTypeConfig | None:
    """Look up a report type by ID.

    Args:
        report_type_id: The report type identifier.

    Returns:
        The ReportTypeConfig, or None if not found.
    """
    return REPORT_TYPES.get(report_type_id)


def list_report_types() -> list[ReportTypeConfig]:
    """Return all registered report types.

    Returns:
        List of all ReportTypeConfig entries.
    """
    return list(REPORT_TYPES.values())
