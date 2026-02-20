import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CreateManualAccountModal } from "../../components/accounts/CreateManualAccountModal";

vi.mock("../../api/accounts", () => ({
  accountsApi: {
    createManual: vi.fn(),
  },
}));

import { accountsApi } from "../../api/accounts";

describe("CreateManualAccountModal", () => {
  const mockOnClose = vi.fn();
  const mockOnCreated = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    render(
      <CreateManualAccountModal
        isOpen={false}
        onClose={mockOnClose}
        onCreated={mockOnCreated}
      />,
    );
    expect(screen.queryByText("Add Manual Account")).not.toBeInTheDocument();
  });

  it("renders form fields when open", () => {
    render(
      <CreateManualAccountModal
        isOpen={true}
        onClose={mockOnClose}
        onCreated={mockOnCreated}
      />,
    );
    expect(screen.getByText("Add Manual Account")).toBeInTheDocument();
    expect(screen.getByTestId("manual-account-name")).toBeInTheDocument();
    expect(screen.getByTestId("manual-account-institution")).toBeInTheDocument();
  });

  it("validates name is required", async () => {
    render(
      <CreateManualAccountModal
        isOpen={true}
        onClose={mockOnClose}
        onCreated={mockOnCreated}
      />,
    );

    fireEvent.click(screen.getByText("Create"));

    await waitFor(() => {
      expect(screen.getByText("Name is required")).toBeInTheDocument();
    });
    expect(accountsApi.createManual).not.toHaveBeenCalled();
  });

  it("calls API on submit", async () => {
    vi.mocked(accountsApi.createManual).mockResolvedValue({ data: { id: "new" } } as unknown as Awaited<ReturnType<typeof accountsApi.createManual>>);

    render(
      <CreateManualAccountModal
        isOpen={true}
        onClose={mockOnClose}
        onCreated={mockOnCreated}
      />,
    );

    fireEvent.change(screen.getByTestId("manual-account-name"), {
      target: { value: "My House" },
    });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() => {
      expect(accountsApi.createManual).toHaveBeenCalledWith({
        name: "My House",
        institution_name: undefined,
      });
    });
  });

  it("calls onCreated and onClose on success", async () => {
    vi.mocked(accountsApi.createManual).mockResolvedValue({ data: { id: "new" } } as unknown as Awaited<ReturnType<typeof accountsApi.createManual>>);

    render(
      <CreateManualAccountModal
        isOpen={true}
        onClose={mockOnClose}
        onCreated={mockOnCreated}
      />,
    );

    fireEvent.change(screen.getByTestId("manual-account-name"), {
      target: { value: "My House" },
    });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() => {
      expect(mockOnCreated).toHaveBeenCalled();
      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  it("shows error on failure", async () => {
    vi.mocked(accountsApi.createManual).mockRejectedValue({
      response: { data: { detail: "Server error" } },
    });

    render(
      <CreateManualAccountModal
        isOpen={true}
        onClose={mockOnClose}
        onCreated={mockOnCreated}
      />,
    );

    fireEvent.change(screen.getByTestId("manual-account-name"), {
      target: { value: "My House" },
    });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() => {
      expect(screen.getByTestId("manual-account-error")).toHaveTextContent("Server error");
    });
    expect(mockOnCreated).not.toHaveBeenCalled();
    expect(mockOnClose).not.toHaveBeenCalled();
  });

  it("calls onClose when Cancel is clicked", () => {
    render(
      <CreateManualAccountModal
        isOpen={true}
        onClose={mockOnClose}
        onCreated={mockOnCreated}
      />,
    );

    fireEvent.click(screen.getByText("Cancel"));
    expect(mockOnClose).toHaveBeenCalled();
  });
});
