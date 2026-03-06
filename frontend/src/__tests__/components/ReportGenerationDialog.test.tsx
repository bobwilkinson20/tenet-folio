import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ReportGenerationDialog } from "../../components/dashboard/ReportGenerationDialog";

vi.mock("../../api/reports", () => ({
  reportsApi: {
    getReportTypes: vi.fn(),
    getTargets: vi.fn(),
    generateGoogleSheets: vi.fn(),
  },
}));

import { reportsApi } from "../../api/reports";

const mockedGetReportTypes = vi.mocked(reportsApi.getReportTypes);
const mockedGetTargets = vi.mocked(reportsApi.getTargets);
const mockedGenerate = vi.mocked(reportsApi.generateGoogleSheets);

const mockTypes = [
  {
    id: "account_allocation",
    display_name: "Account Allocation",
    description: "Test",
    config_fields: [],
  },
];

const mockTargets = [
  {
    id: "target-1",
    report_type: "account_allocation",
    spreadsheet_id: "sheet123",
    display_name: "My Portfolio Sheet",
    config: { template_tab: "Template" },
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  },
];

describe("ReportGenerationDialog", () => {
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when closed", () => {
    render(
      <ReportGenerationDialog
        isOpen={false}
        onClose={onClose}
        allocationOnly={false}
      />,
    );

    expect(screen.queryByText("Generate Report")).not.toBeInTheDocument();
  });

  it("shows loading state", () => {
    mockedGetReportTypes.mockReturnValue(new Promise(() => {}) as never);
    mockedGetTargets.mockReturnValue(new Promise(() => {}) as never);

    render(
      <ReportGenerationDialog
        isOpen={true}
        onClose={onClose}
        allocationOnly={false}
      />,
    );

    expect(screen.getByTestId("report-dialog-loading")).toBeInTheDocument();
  });

  it("auto-selects single type and single target", async () => {
    mockedGetReportTypes.mockResolvedValue({ data: mockTypes } as never);
    mockedGetTargets.mockResolvedValue({ data: mockTargets } as never);

    render(
      <ReportGenerationDialog
        isOpen={true}
        onClose={onClose}
        allocationOnly={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("auto-selected-target")).toBeInTheDocument();
    });

    expect(screen.getByText("My Portfolio Sheet")).toBeInTheDocument();
    expect(screen.getByTestId("generate-btn")).not.toBeDisabled();
  });

  it("shows no-targets message when none exist", async () => {
    mockedGetReportTypes.mockResolvedValue({ data: mockTypes } as never);
    mockedGetTargets.mockResolvedValue({ data: [] } as never);

    render(
      <ReportGenerationDialog
        isOpen={true}
        onClose={onClose}
        allocationOnly={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("no-targets-message")).toBeInTheDocument();
    });

    expect(screen.getByText(/Settings > Reports/)).toBeInTheDocument();
  });

  it("generates report and shows result", async () => {
    mockedGetReportTypes.mockResolvedValue({ data: mockTypes } as never);
    mockedGetTargets.mockResolvedValue({ data: mockTargets } as never);
    mockedGenerate.mockResolvedValue({
      data: { tab_name: "2026-03-06 14:30 UTC", rows_written: 5 },
    } as never);

    render(
      <ReportGenerationDialog
        isOpen={true}
        onClose={onClose}
        allocationOnly={true}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("generate-btn")).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId("generate-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("report-dialog-success")).toBeInTheDocument();
    });

    expect(screen.getByText("2026-03-06 14:30 UTC")).toBeInTheDocument();
    expect(screen.getByText(/5 rows/)).toBeInTheDocument();

    expect(mockedGenerate).toHaveBeenCalledWith({
      target_id: "target-1",
      allocation_only: true,
    });
  });

  it("shows error on generation failure", async () => {
    mockedGetReportTypes.mockResolvedValue({ data: mockTypes } as never);
    mockedGetTargets.mockResolvedValue({ data: mockTargets } as never);
    mockedGenerate.mockRejectedValue({
      response: { data: { detail: "Sheets API error" } },
    });

    render(
      <ReportGenerationDialog
        isOpen={true}
        onClose={onClose}
        allocationOnly={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("generate-btn")).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId("generate-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("report-dialog-error")).toBeInTheDocument();
    });

    expect(screen.getByText("Sheets API error")).toBeInTheDocument();
  });

  it("shows target selector when multiple targets exist", async () => {
    const multiTargets = [
      ...mockTargets,
      {
        id: "target-2",
        report_type: "account_allocation",
        spreadsheet_id: "sheet456",
        display_name: "Second Sheet",
        config: { template_tab: "Template" },
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
      },
    ];

    mockedGetReportTypes.mockResolvedValue({ data: mockTypes } as never);
    mockedGetTargets.mockResolvedValue({ data: multiTargets } as never);

    render(
      <ReportGenerationDialog
        isOpen={true}
        onClose={onClose}
        allocationOnly={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("report-target-select")).toBeInTheDocument();
    });

    // Generate should be disabled until target selected
    expect(screen.getByTestId("generate-btn")).toBeDisabled();
  });

  it("cancel closes dialog", async () => {
    mockedGetReportTypes.mockResolvedValue({ data: mockTypes } as never);
    mockedGetTargets.mockResolvedValue({ data: mockTargets } as never);

    render(
      <ReportGenerationDialog
        isOpen={true}
        onClose={onClose}
        allocationOnly={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("generate-btn")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
  });
});
