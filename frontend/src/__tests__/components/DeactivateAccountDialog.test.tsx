import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DeactivateAccountDialog } from "../../components/accounts/DeactivateAccountDialog";
import type { Account } from "../../types";

const mockDeactivate = vi.fn();

vi.mock("@/api/accounts", () => ({
  accountsApi: {
    deactivate: (...args: unknown[]) => mockDeactivate(...args),
  },
}));

const makeAccount = (overrides: Partial<Account> = {}): Account => ({
  id: "acct-1",
  provider_name: "SimpleFIN",
  external_id: "sf_1",
  name: "Vanguard Brokerage",
  institution_name: "Vanguard",
  is_active: true,
  include_in_allocation: true,
  assigned_asset_class_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
  value: "10000.00",
  ...overrides,
});

const makePlaidAccount = (): Account => ({
  id: "acct-2",
  provider_name: "Plaid",
  external_id: "plaid_1",
  name: "Vanguard via Plaid",
  institution_name: "Vanguard",
  is_active: true,
  include_in_allocation: true,
  assigned_asset_class_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
});

describe("DeactivateAccountDialog", () => {
  const onClose = vi.fn();
  const onDeactivated = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when account is null", () => {
    const { container } = render(
      <DeactivateAccountDialog
        isOpen={true}
        account={null}
        allAccounts={[]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders account name in the dialog", () => {
    render(
      <DeactivateAccountDialog
        isOpen={true}
        account={makeAccount()}
        allAccounts={[]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );
    expect(screen.getByText("Vanguard Brokerage")).toBeInTheDocument();
  });

  it("shows closing snapshot checkbox when account has value", () => {
    render(
      <DeactivateAccountDialog
        isOpen={true}
        account={makeAccount({ value: "10000.00" })}
        allAccounts={[]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );
    expect(screen.getByTestId("closing-snapshot-checkbox")).toBeInTheDocument();
    expect(screen.getByTestId("closing-snapshot-checkbox")).toBeChecked();
  });

  it("hides closing snapshot checkbox when account has no value", () => {
    render(
      <DeactivateAccountDialog
        isOpen={true}
        account={makeAccount({ value: null })}
        allAccounts={[]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );
    expect(screen.queryByTestId("closing-snapshot-checkbox")).not.toBeInTheDocument();
  });

  it("shows replacement picker with other active accounts", () => {
    const account = makeAccount();
    const plaid = makePlaidAccount();
    render(
      <DeactivateAccountDialog
        isOpen={true}
        account={account}
        allAccounts={[account, plaid]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );
    expect(screen.getByTestId("superseded-by-select")).toBeInTheDocument();
    expect(screen.getByText(/Vanguard via Plaid/)).toBeInTheDocument();
  });

  it("excludes the current account from the replacement picker", () => {
    const account = makeAccount();
    render(
      <DeactivateAccountDialog
        isOpen={true}
        account={account}
        allAccounts={[account]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );
    // No candidates other than self, so picker is hidden
    expect(screen.queryByTestId("superseded-by-select")).not.toBeInTheDocument();
  });

  it("calls deactivate API with correct args on confirm", async () => {
    mockDeactivate.mockResolvedValue({ data: { ...makeAccount(), is_active: false } });
    const user = userEvent.setup();

    render(
      <DeactivateAccountDialog
        isOpen={true}
        account={makeAccount()}
        allAccounts={[]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );

    await user.click(screen.getByTestId("confirm-deactivate-account"));

    await waitFor(() => {
      expect(mockDeactivate).toHaveBeenCalledWith("acct-1", {
        create_closing_snapshot: true,
        superseded_by_account_id: null,
      });
    });
  });

  it("calls onDeactivated and onClose after successful deactivation", async () => {
    const deactivated = { ...makeAccount(), is_active: false };
    mockDeactivate.mockResolvedValue({ data: deactivated });
    const user = userEvent.setup();

    render(
      <DeactivateAccountDialog
        isOpen={true}
        account={makeAccount()}
        allAccounts={[]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );

    await user.click(screen.getByTestId("confirm-deactivate-account"));

    await waitFor(() => {
      expect(onDeactivated).toHaveBeenCalledWith(deactivated);
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("calls deactivate with closing_snapshot=false when unchecked", async () => {
    mockDeactivate.mockResolvedValue({ data: { ...makeAccount(), is_active: false } });
    const user = userEvent.setup();

    render(
      <DeactivateAccountDialog
        isOpen={true}
        account={makeAccount()}
        allAccounts={[]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );

    await user.click(screen.getByTestId("closing-snapshot-checkbox"));
    await user.click(screen.getByTestId("confirm-deactivate-account"));

    await waitFor(() => {
      expect(mockDeactivate).toHaveBeenCalledWith("acct-1", {
        create_closing_snapshot: false,
        superseded_by_account_id: null,
      });
    });
  });

  it("shows error message when API call fails", async () => {
    mockDeactivate.mockRejectedValue({
      response: { data: { detail: "Account is already inactive" } },
    });
    const user = userEvent.setup();

    render(
      <DeactivateAccountDialog
        isOpen={true}
        account={makeAccount()}
        allAccounts={[]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );

    await user.click(screen.getByTestId("confirm-deactivate-account"));

    await waitFor(() => {
      expect(screen.getByTestId("deactivate-account-error")).toHaveTextContent(
        "Account is already inactive"
      );
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose when Cancel is clicked", async () => {
    const user = userEvent.setup();

    render(
      <DeactivateAccountDialog
        isOpen={true}
        account={makeAccount()}
        allAccounts={[]}
        onClose={onClose}
        onDeactivated={onDeactivated}
      />
    );

    await user.click(screen.getByText("Cancel"));
    expect(onClose).toHaveBeenCalled();
  });
});
