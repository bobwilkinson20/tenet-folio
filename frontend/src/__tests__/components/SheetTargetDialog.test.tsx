import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SheetTargetDialog } from "../../components/settings/SheetTargetDialog";

vi.mock("../../api/reports", () => ({
  reportsApi: {
    createTarget: vi.fn(),
    updateTarget: vi.fn(),
  },
}));

import { reportsApi } from "../../api/reports";

const mockedCreateTarget = vi.mocked(reportsApi.createTarget);
const mockedUpdateTarget = vi.mocked(reportsApi.updateTarget);

const mockReportTypes = [
  {
    id: "account_allocation",
    display_name: "Account Allocation",
    description: "Test",
    config_fields: [
      {
        key: "template_tab",
        label: "Template Tab",
        help_text: "Tab name to duplicate",
        required: true,
        default: "Template",
      },
    ],
  },
];

describe("SheetTargetDialog", () => {
  const onClose = vi.fn();
  const onSaved = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when closed", () => {
    render(
      <SheetTargetDialog
        isOpen={false}
        onClose={onClose}
        onSaved={onSaved}
        reportTypes={mockReportTypes}
        editingTarget={null}
      />,
    );

    expect(screen.queryByText("Add Sheet Target")).not.toBeInTheDocument();
  });

  describe("create mode", () => {
    it("renders form fields", () => {
      render(
        <SheetTargetDialog
          isOpen={true}
          onClose={onClose}
          onSaved={onSaved}
          reportTypes={mockReportTypes}
          editingTarget={null}
        />,
      );

      expect(screen.getByText("Add Sheet Target")).toBeInTheDocument();
      expect(screen.getByTestId("spreadsheet-id-input")).toBeInTheDocument();
      expect(screen.getByTestId("display-name-input")).toBeInTheDocument();
    });

    it("auto-selects report type when only one exists", () => {
      render(
        <SheetTargetDialog
          isOpen={true}
          onClose={onClose}
          onSaved={onSaved}
          reportTypes={mockReportTypes}
          editingTarget={null}
        />,
      );

      const select = screen.getByTestId("report-type-select") as HTMLSelectElement;
      expect(select.value).toBe("account_allocation");
    });

    it("shows dynamic config fields with defaults", () => {
      render(
        <SheetTargetDialog
          isOpen={true}
          onClose={onClose}
          onSaved={onSaved}
          reportTypes={mockReportTypes}
          editingTarget={null}
        />,
      );

      const templateField = screen.getByTestId("config-field-template_tab") as HTMLInputElement;
      expect(templateField.value).toBe("Template");
      expect(screen.getByText("Tab name to duplicate")).toBeInTheDocument();
    });

    it("submits and calls onSaved", async () => {
      mockedCreateTarget.mockResolvedValue({
        data: {
          id: "new-1",
          report_type: "account_allocation",
          spreadsheet_id: "sheet123",
          display_name: "Test",
          config: { template_tab: "Template" },
          created_at: "2026-01-01",
          updated_at: "2026-01-01",
        },
      } as never);

      render(
        <SheetTargetDialog
          isOpen={true}
          onClose={onClose}
          onSaved={onSaved}
          reportTypes={mockReportTypes}
          editingTarget={null}
        />,
      );

      fireEvent.change(screen.getByTestId("spreadsheet-id-input"), {
        target: { value: "sheet123" },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save" }));

      await waitFor(() => {
        expect(mockedCreateTarget).toHaveBeenCalledWith({
          report_type: "account_allocation",
          spreadsheet_id: "sheet123",
          display_name: undefined,
          config: { template_tab: "Template" },
        });
      });

      expect(onSaved).toHaveBeenCalled();
    });

    it("shows error on submit failure", async () => {
      mockedCreateTarget.mockRejectedValue({
        response: { data: { detail: "Spreadsheet not accessible" } },
      });

      render(
        <SheetTargetDialog
          isOpen={true}
          onClose={onClose}
          onSaved={onSaved}
          reportTypes={mockReportTypes}
          editingTarget={null}
        />,
      );

      fireEvent.change(screen.getByTestId("spreadsheet-id-input"), {
        target: { value: "bad-id" },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save" }));

      await waitFor(() => {
        expect(screen.getByTestId("target-error")).toHaveTextContent(
          "Spreadsheet not accessible",
        );
      });

      expect(onSaved).not.toHaveBeenCalled();
    });
  });

  describe("edit mode", () => {
    const editTarget = {
      id: "target-1",
      report_type: "account_allocation",
      spreadsheet_id: "sheet123",
      display_name: "Existing Sheet",
      config: { template_tab: "MyTemplate" },
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };

    it("shows edit title and readonly fields", () => {
      render(
        <SheetTargetDialog
          isOpen={true}
          onClose={onClose}
          onSaved={onSaved}
          reportTypes={mockReportTypes}
          editingTarget={editTarget}
        />,
      );

      expect(screen.getByText("Edit Sheet Target")).toBeInTheDocument();
      expect(screen.getByTestId("report-type-readonly")).toBeInTheDocument();
      expect(screen.getByTestId("spreadsheet-id-readonly")).toBeInTheDocument();
    });

    it("pre-fills editable fields", () => {
      render(
        <SheetTargetDialog
          isOpen={true}
          onClose={onClose}
          onSaved={onSaved}
          reportTypes={mockReportTypes}
          editingTarget={editTarget}
        />,
      );

      const displayName = screen.getByTestId("display-name-input") as HTMLInputElement;
      expect(displayName.value).toBe("Existing Sheet");

      const templateTab = screen.getByTestId("config-field-template_tab") as HTMLInputElement;
      expect(templateTab.value).toBe("MyTemplate");
    });

    it("submits update", async () => {
      mockedUpdateTarget.mockResolvedValue({
        data: { ...editTarget, display_name: "Updated Name" },
      } as never);

      render(
        <SheetTargetDialog
          isOpen={true}
          onClose={onClose}
          onSaved={onSaved}
          reportTypes={mockReportTypes}
          editingTarget={editTarget}
        />,
      );

      fireEvent.change(screen.getByTestId("display-name-input"), {
        target: { value: "Updated Name" },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save" }));

      await waitFor(() => {
        expect(mockedUpdateTarget).toHaveBeenCalledWith("target-1", {
          display_name: "Updated Name",
          config: { template_tab: "MyTemplate" },
        });
      });

      expect(onSaved).toHaveBeenCalled();
    });
  });

  it("cancel closes dialog", () => {
    render(
      <SheetTargetDialog
        isOpen={true}
        onClose={onClose}
        onSaved={onSaved}
        reportTypes={mockReportTypes}
        editingTarget={null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
  });
});
