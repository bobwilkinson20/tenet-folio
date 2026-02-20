import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { EditAccountDialog } from "../../components/accounts/EditAccountDialog";
import type { Account } from "../../types";

vi.mock("../../api/assetTypes", () => ({
  assetTypeApi: {
    list: vi.fn().mockResolvedValue({ data: { items: [] } }),
  },
}));

import { accountsApi } from "../../api/accounts";

vi.mock("../../api/accounts", () => ({
  accountsApi: {
    update: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

const testAccount: Account = {
  id: "acc-1",
  name: "Test Account",
  provider_name: "SnapTrade",
  institution_name: "Vanguard",
  external_id: "ext-1",
  is_active: true,
  account_type: "roth_ira",
  include_in_allocation: true,
  assigned_asset_class_id: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  value: "50000.00",
};

describe("EditAccountDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    render(
      <EditAccountDialog
        isOpen={false}
        account={testAccount}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    expect(screen.queryByText("Edit Account")).not.toBeInTheDocument();
  });

  it("renders when isOpen is true", () => {
    render(
      <EditAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    expect(screen.getByText("Edit Account")).toBeInTheDocument();
  });

  it("populates fields with account data", () => {
    render(
      <EditAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    expect(screen.getByTestId("edit-account-name")).toHaveValue("Test Account");
    expect(screen.getByTestId("edit-account-type")).toHaveTextContent("Roth IRA");
    expect(screen.getByTestId("edit-include-in-allocation")).toBeChecked();
  });

  it("calls onClose when Cancel is clicked", () => {
    const onClose = vi.fn();
    render(
      <EditAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={onClose}
        onSaved={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("Cancel"));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls API and onSaved when Save is clicked with changes", async () => {
    const onSaved = vi.fn();
    const onClose = vi.fn();
    vi.mocked(accountsApi.update).mockResolvedValueOnce({
      data: { ...testAccount, name: "Updated Name" },
    } as never);

    render(
      <EditAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={onClose}
        onSaved={onSaved}
      />,
    );

    const nameInput = screen.getByTestId("edit-account-name");
    fireEvent.change(nameInput, { target: { value: "Updated Name" } });
    fireEvent.click(screen.getByTestId("edit-account-save"));

    await waitFor(() => {
      expect(accountsApi.update).toHaveBeenCalledWith("acc-1", {
        name: "Updated Name",
      });
      expect(onSaved).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("closes without API call when no changes are made", () => {
    const onClose = vi.fn();
    render(
      <EditAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={onClose}
        onSaved={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("edit-account-save"));

    expect(accountsApi.update).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("shows error for empty name", async () => {
    render(
      <EditAccountDialog
        isOpen={true}
        account={testAccount}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    const nameInput = screen.getByTestId("edit-account-name");
    fireEvent.change(nameInput, { target: { value: "" } });
    fireEvent.click(screen.getByTestId("edit-account-save"));

    await waitFor(() => {
      expect(screen.getByText("Name is required")).toBeInTheDocument();
    });
  });
});
