import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ReportResultModal } from "../../components/dashboard/ReportResultModal";

describe("ReportResultModal", () => {
  const mockClose = vi.fn();

  it("is hidden when not open", () => {
    render(
      <ReportResultModal
        isOpen={false}
        onClose={mockClose}
        generating={false}
        result={null}
        errorMessage={null}
      />
    );

    expect(
      screen.queryByTestId("report-result-modal")
    ).not.toBeInTheDocument();
  });

  it("shows loading state when generating", () => {
    render(
      <ReportResultModal
        isOpen={true}
        onClose={mockClose}
        generating={true}
        result={null}
        errorMessage={null}
      />
    );

    expect(screen.getByTestId("report-loading")).toBeInTheDocument();
    expect(screen.getByText(/generating report/i)).toBeInTheDocument();
  });

  it("shows success result with tab name and row count", () => {
    render(
      <ReportResultModal
        isOpen={true}
        onClose={mockClose}
        generating={false}
        result={{ tab_name: "2026-02-25 14:30 UTC", rows_written: 5 }}
        errorMessage={null}
      />
    );

    expect(screen.getByTestId("report-success")).toBeInTheDocument();
    expect(screen.getByText("2026-02-25 14:30 UTC")).toBeInTheDocument();
    expect(screen.getByText(/5 rows/)).toBeInTheDocument();
  });

  it("shows singular row when rows_written is 1", () => {
    render(
      <ReportResultModal
        isOpen={true}
        onClose={mockClose}
        generating={false}
        result={{ tab_name: "2026-02-25 14:30 UTC", rows_written: 1 }}
        errorMessage={null}
      />
    );

    expect(screen.getByText(/1 row\b/)).toBeInTheDocument();
  });

  it("shows error message", () => {
    render(
      <ReportResultModal
        isOpen={true}
        onClose={mockClose}
        generating={false}
        result={null}
        errorMessage="Google Sheets is not configured."
      />
    );

    expect(screen.getByTestId("report-error")).toBeInTheDocument();
    expect(
      screen.getByText("Google Sheets is not configured.")
    ).toBeInTheDocument();
  });

  it("calls onClose when close button clicked", () => {
    render(
      <ReportResultModal
        isOpen={true}
        onClose={mockClose}
        generating={false}
        result={{ tab_name: "tab", rows_written: 1 }}
        errorMessage={null}
      />
    );

    fireEvent.click(screen.getByTestId("report-result-close"));
    expect(mockClose).toHaveBeenCalled();
  });
});
