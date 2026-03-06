import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ReportsSettings } from "../../components/settings/ReportsSettings";

vi.mock("../../api/reports", () => ({
  reportsApi: {
    getCredentialStatus: vi.fn(),
    setCredentials: vi.fn(),
    removeCredentials: vi.fn(),
    getReportTypes: vi.fn(),
    getTargets: vi.fn(),
    createTarget: vi.fn(),
    updateTarget: vi.fn(),
    deleteTarget: vi.fn(),
  },
}));

import { reportsApi } from "../../api/reports";

const mockedGetCredentialStatus = vi.mocked(reportsApi.getCredentialStatus);
const mockedSetCredentials = vi.mocked(reportsApi.setCredentials);
const mockedRemoveCredentials = vi.mocked(reportsApi.removeCredentials);
const mockedGetReportTypes = vi.mocked(reportsApi.getReportTypes);
const mockedGetTargets = vi.mocked(reportsApi.getTargets);
const mockedDeleteTarget = vi.mocked(reportsApi.deleteTarget);

const mockReportTypes = [
  {
    id: "account_allocation",
    display_name: "Account Allocation",
    description: "Test description",
    config_fields: [
      { key: "template_tab", label: "Template Tab", required: true, default: "Template" },
    ],
  },
];

describe("ReportsSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetReportTypes.mockResolvedValue({ data: mockReportTypes } as never);
  });

  describe("unconfigured state", () => {
    beforeEach(() => {
      mockedGetCredentialStatus.mockResolvedValue({
        data: { configured: false, service_account_email: null },
      } as never);
      mockedGetTargets.mockResolvedValue({ data: [] } as never);
    });

    it("shows Configure button when not configured", async () => {
      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByTestId("configure-credentials-btn")).toBeInTheDocument();
      });

      expect(screen.queryByText("Configured")).not.toBeInTheDocument();
      // Sheet targets should not be visible when not configured
      expect(screen.queryByText("Sheet Targets")).not.toBeInTheDocument();
    });

    it("shows credential form when Configure is clicked", async () => {
      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByTestId("configure-credentials-btn")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("configure-credentials-btn"));

      expect(screen.getByTestId("credentials-json-input")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    });
  });

  describe("configured state", () => {
    beforeEach(() => {
      mockedGetCredentialStatus.mockResolvedValue({
        data: {
          configured: true,
          service_account_email: "test@example.iam.gserviceaccount.com",
        },
      } as never);
      mockedGetTargets.mockResolvedValue({ data: [] } as never);
    });

    it("shows configured status with email", async () => {
      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByText("Configured")).toBeInTheDocument();
      });

      expect(screen.getByTestId("service-account-email")).toHaveTextContent(
        "test@example.iam.gserviceaccount.com",
      );
    });

    it("shows Reconfigure and Remove buttons", async () => {
      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByText("Configured")).toBeInTheDocument();
      });

      expect(screen.getByRole("button", { name: "Reconfigure" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
    });

    it("shows Sheet Targets section", async () => {
      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByText("Sheet Targets")).toBeInTheDocument();
      });

      expect(screen.getByTestId("add-target-btn")).toBeInTheDocument();
    });

    it("handles remove credentials", async () => {
      mockedRemoveCredentials.mockResolvedValue({} as never);

      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByText("Configured")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: "Remove" }));

      await waitFor(() => {
        expect(mockedRemoveCredentials).toHaveBeenCalled();
      });
    });
  });

  describe("credential configuration", () => {
    beforeEach(() => {
      mockedGetCredentialStatus.mockResolvedValue({
        data: { configured: false, service_account_email: null },
      } as never);
      mockedGetTargets.mockResolvedValue({ data: [] } as never);
    });

    it("submits credentials and shows configured state", async () => {
      mockedSetCredentials.mockResolvedValue({
        data: {
          configured: true,
          service_account_email: "new@example.iam.gserviceaccount.com",
        },
      } as never);

      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByTestId("configure-credentials-btn")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("configure-credentials-btn"));

      const textarea = screen.getByTestId("credentials-json-input");
      fireEvent.change(textarea, {
        target: { value: '{"client_email": "new@example.iam.gserviceaccount.com", "private_key": "pk"}' },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save" }));

      await waitFor(() => {
        expect(mockedSetCredentials).toHaveBeenCalled();
      });
    });

    it("shows error on credential save failure", async () => {
      mockedSetCredentials.mockRejectedValue({
        response: { data: { detail: "Invalid JSON format" } },
      });

      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByTestId("configure-credentials-btn")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("configure-credentials-btn"));

      const textarea = screen.getByTestId("credentials-json-input");
      fireEvent.change(textarea, { target: { value: "bad json" } });

      fireEvent.click(screen.getByRole("button", { name: "Save" }));

      await waitFor(() => {
        expect(screen.getByTestId("credential-error")).toHaveTextContent(
          "Invalid JSON format",
        );
      });
    });
  });

  describe("sheet targets", () => {
    const mockTargets = [
      {
        id: "target-1",
        report_type: "account_allocation",
        spreadsheet_id: "sheet123",
        display_name: "My Portfolio Sheet",
        config: { template_tab: "Template" },
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];

    beforeEach(() => {
      mockedGetCredentialStatus.mockResolvedValue({
        data: {
          configured: true,
          service_account_email: "test@example.iam.gserviceaccount.com",
        },
      } as never);
      mockedGetTargets.mockResolvedValue({ data: mockTargets } as never);
    });

    it("lists targets", async () => {
      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByText("My Portfolio Sheet")).toBeInTheDocument();
      });

      expect(screen.getByText(/Account Allocation/)).toBeInTheDocument();
    });

    it("deletes a target with confirmation", async () => {
      mockedDeleteTarget.mockResolvedValue({} as never);

      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByText("My Portfolio Sheet")).toBeInTheDocument();
      });

      // Click delete
      fireEvent.click(screen.getByRole("button", { name: "Delete" }));

      // Confirm
      fireEvent.click(screen.getByTestId("confirm-delete-btn"));

      await waitFor(() => {
        expect(mockedDeleteTarget).toHaveBeenCalledWith("target-1");
      });
    });

    it("cancels delete", async () => {
      render(<ReportsSettings />);

      await waitFor(() => {
        expect(screen.getByText("My Portfolio Sheet")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: "Delete" }));

      // Cancel confirmation
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

      // Delete button should be visible again
      expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
      expect(mockedDeleteTarget).not.toHaveBeenCalled();
    });
  });
});
