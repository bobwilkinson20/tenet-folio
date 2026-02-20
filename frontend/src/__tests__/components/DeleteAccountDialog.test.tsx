import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DeleteAccountDialog } from "../../components/accounts/DeleteAccountDialog";
import type { Account } from "../../types";

import { accountsApi } from "../../api/accounts";

vi.mock("../../api/accounts", () => ({
  accountsApi: {
    delete: vi.fn().mockResolvedValue({}),
  },
}));

const testAccount: Account = {
  id: "acc-1",
  name: "Test Account",
  provider_name: "SnapTrade",
  institution_name: "Vanguard",
  external_id: "ext-1",
  is_active: true,
  account_type: null,
  include_in_allocation: true,
  assigned_asset_class_id: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  value: "50000.00",
};

describe("DeleteAccountDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    render(
      <DeleteAccountDialog
        isOpen={false}
        account={testAccount}
        onClose={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );

    expect(screen.queryByText("Delete Account")).not.toBeInTheDocument();
  });

  it("renders with account name when isOpen is true", () => {
    render(
      <DeleteAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );

    expect(screen.getByText("Delete Account")).toBeInTheDocument();
    expect(screen.getByText("Test Account")).toBeInTheDocument();
  });

  it("calls onClose when Cancel is clicked", () => {
    const onClose = vi.fn();
    render(
      <DeleteAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={onClose}
        onDeleted={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("Cancel"));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls API and onDeleted when Delete is confirmed", async () => {
    const onDeleted = vi.fn();
    const onClose = vi.fn();

    render(
      <DeleteAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={onClose}
        onDeleted={onDeleted}
      />,
    );

    fireEvent.click(screen.getByTestId("confirm-delete-account"));

    await waitFor(() => {
      expect(accountsApi.delete).toHaveBeenCalledWith("acc-1");
      expect(onDeleted).toHaveBeenCalledWith("acc-1");
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("shows re-sync warning for synced accounts", () => {
    render(
      <DeleteAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );

    expect(screen.getByText(/will be recreated on the next sync/)).toBeInTheDocument();
    expect(screen.getByText("SnapTrade")).toBeInTheDocument();
  });

  it("shows permanent warning for manual accounts", () => {
    const manualAccount: Account = {
      ...testAccount,
      id: "acc-manual",
      provider_name: "Manual",
      name: "My House",
    };

    render(
      <DeleteAccountDialog
        isOpen={true}
        account={manualAccount}
        onClose={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );

    expect(screen.getByText(/This is permanent/)).toBeInTheDocument();
    expect(screen.queryByText(/will be recreated on the next sync/)).not.toBeInTheDocument();
  });

  it("shows error message on API failure", async () => {
    vi.mocked(accountsApi.delete).mockRejectedValueOnce(
      new Error("Network error"),
    );

    render(
      <DeleteAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("confirm-delete-account"));

    await waitFor(() => {
      expect(screen.getByTestId("delete-account-error")).toBeInTheDocument();
    });
  });
});
