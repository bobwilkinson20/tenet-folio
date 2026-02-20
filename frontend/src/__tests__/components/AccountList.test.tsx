import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { AccountList } from "../../components/accounts/AccountList";
import type { AccountListProps } from "../../components/accounts/AccountList";
import type { Account } from "../../types";

function renderAccountList(props: AccountListProps) {
  return render(
    <MemoryRouter>
      <AccountList {...props} />
    </MemoryRouter>
  );
}

describe("AccountList", () => {
  const mockEdit = vi.fn();
  const mockToggleActive = vi.fn();
  const mockDelete = vi.fn();

  const baseAccounts: Account[] = [
    {
      id: "acc-1",
      name: "Brokerage Account",
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
      last_sync_time: "2026-01-29T10:30:00Z",
      last_sync_status: "success",
      balance_date: "2026-01-28T12:00:00Z",
    },
    {
      id: "acc-2",
      name: "Retirement Account",
      provider_name: "SimpleFIN",
      institution_name: null,
      external_id: "ext-2",
      is_active: true,
      account_type: "roth_ira",
      include_in_allocation: true,
      assigned_asset_class_id: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
      value: "75000.00",
      last_sync_time: null,
      last_sync_status: null,
      balance_date: null,
    },
    {
      id: "acc-3",
      name: "Empty Account",
      provider_name: "SnapTrade",
      institution_name: "Fidelity",
      external_id: "ext-3",
      is_active: false,
      account_type: null,
      include_in_allocation: false,
      assigned_asset_class_id: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
      value: null,
      last_sync_time: null,
      last_sync_status: null,
      balance_date: null,
    },
  ];

  it("renders loading state", () => {
    renderAccountList({
      accounts: [],
      loading: true,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    expect(screen.getByText(/loading accounts/i)).toBeInTheDocument();
  });

  it("renders empty state when no accounts", () => {
    renderAccountList({
      accounts: [],
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    expect(screen.getByText(/no accounts found/i)).toBeInTheDocument();
  });

  it("displays institution name under account name", () => {
    renderAccountList({
      accounts: baseAccounts,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    expect(screen.getByText("Vanguard")).toBeInTheDocument();
    expect(screen.getByText("Fidelity")).toBeInTheDocument();
  });

  it("falls back to provider_name when institution_name is null", () => {
    renderAccountList({
      accounts: baseAccounts,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    // SimpleFIN appears as institution fallback under account name
    const simplefinElements = screen.getAllByText("SimpleFIN");
    expect(simplefinElements.length).toBeGreaterThan(0);
  });

  it("shows column headers", () => {
    renderAccountList({
      accounts: baseAccounts,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    expect(screen.getByText("Account")).toBeInTheDocument();
    expect(screen.getByText("Value")).toBeInTheDocument();
    expect(screen.getByText("Account Type")).toBeInTheDocument();
    expect(screen.getByText("Included")).toBeInTheDocument();
  });

  it("displays formatted currency values", () => {
    renderAccountList({
      accounts: baseAccounts,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    expect(screen.getByText("$50,000.00")).toBeInTheDocument();
    expect(screen.getByText("$75,000.00")).toBeInTheDocument();
  });

  it("displays dash for null value", () => {
    renderAccountList({
      accounts: baseAccounts,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    const dashes = screen.getAllByText("-");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("displays sync status icons for accounts", () => {
    renderAccountList({
      accounts: baseAccounts,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    // acc-1 has recent sync — but the test date is in 2026 and Date.now() may differ,
    // so it could be green or yellow depending on when tests run.
    // acc-2 and acc-3 have no last_sync_time — should show yellow warning
    expect(screen.getByTestId("sync-warning-acc-2")).toBeInTheDocument();
    expect(screen.getByTestId("sync-warning-acc-3")).toBeInTheDocument();
  });

  it("renders account names as links to account details", () => {
    renderAccountList({
      accounts: baseAccounts,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    const link1 = screen.getByRole("link", { name: "Brokerage Account" });
    expect(link1).toHaveAttribute("href", "/accounts/acc-1");

    const link2 = screen.getByRole("link", { name: "Retirement Account" });
    expect(link2).toHaveAttribute("href", "/accounts/acc-2");

    const link3 = screen.getByRole("link", { name: "Empty Account" });
    expect(link3).toHaveAttribute("href", "/accounts/acc-3");
  });

  it("shows account type badge for typed accounts", () => {
    renderAccountList({
      accounts: baseAccounts,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    expect(screen.getByTestId("account-type-badge-acc-2")).toHaveTextContent("Roth IRA");
  });

  it("shows checkmark for accounts included in allocation", () => {
    renderAccountList({
      accounts: baseAccounts,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    // acc-1 and acc-2 are include_in_allocation=true, should have checkmark SVGs
    const allocCell1 = screen.getByTestId("alloc-acc-1");
    expect(allocCell1.querySelector("svg")).toBeInTheDocument();

    // acc-3 has include_in_allocation=false, should have dash
    const allocCell3 = screen.getByTestId("alloc-acc-3");
    expect(allocCell3).toHaveTextContent("-");
  });

  it("shows read-only asset type badge with color", () => {
    const accountsWithAssetType: Account[] = [
      {
        ...baseAccounts[0],
        assigned_asset_class_id: "ac-1",
        assigned_asset_class_name: "Stocks",
        assigned_asset_class_color: "#3B82F6",
      },
    ];

    renderAccountList({
      accounts: accountsWithAssetType,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    expect(screen.getByText("Stocks")).toBeInTheDocument();
  });

  it("renders kebab menu for each account", () => {
    renderAccountList({
      accounts: baseAccounts,
      loading: false,
      onEdit: mockEdit,
      onToggleActive: mockToggleActive,
      onDelete: mockDelete,
    });

    expect(screen.getByTestId("account-actions-acc-1")).toBeInTheDocument();
    expect(screen.getByTestId("account-actions-acc-2")).toBeInTheDocument();
    expect(screen.getByTestId("account-actions-acc-3")).toBeInTheDocument();
  });

  describe("sorting", () => {
    it("sorts by name ascending when Account header is clicked", () => {
      renderAccountList({
        accounts: baseAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const nameHeader = screen.getByText("Account");
      fireEvent.click(nameHeader);

      const rows = screen.getAllByRole("row");
      expect(rows[1]).toHaveTextContent("Brokerage Account");
      expect(rows[2]).toHaveTextContent("Empty Account");
      expect(rows[3]).toHaveTextContent("Retirement Account");
    });

    it("sorts by name descending on second click", () => {
      renderAccountList({
        accounts: baseAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const nameHeader = screen.getByText("Account");
      fireEvent.click(nameHeader);
      fireEvent.click(nameHeader);

      const rows = screen.getAllByRole("row");
      expect(rows[1]).toHaveTextContent("Retirement Account");
      expect(rows[2]).toHaveTextContent("Empty Account");
      expect(rows[3]).toHaveTextContent("Brokerage Account");
    });

    it("resets sort on third click", () => {
      renderAccountList({
        accounts: baseAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const nameHeader = screen.getByText("Account");
      fireEvent.click(nameHeader);
      fireEvent.click(nameHeader);
      fireEvent.click(nameHeader);

      const rows = screen.getAllByRole("row");
      expect(rows[1]).toHaveTextContent("Brokerage Account");
      expect(rows[2]).toHaveTextContent("Retirement Account");
      expect(rows[3]).toHaveTextContent("Empty Account");
    });

    it("shows sort indicator when sorted", async () => {
      renderAccountList({
        accounts: baseAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const nameHeader = screen.getByText("Account");
      fireEvent.click(nameHeader);

      await waitFor(() => {
        expect(screen.getByText(/Account.*▲/)).toBeInTheDocument();
      });

      fireEvent.click(nameHeader);

      await waitFor(() => {
        expect(screen.getByText(/Account.*▼/)).toBeInTheDocument();
      });
    });

    it("sorts by value correctly", () => {
      renderAccountList({
        accounts: baseAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const valueHeader = screen.getByText("Value");
      fireEvent.click(valueHeader);

      const rows = screen.getAllByRole("row");
      expect(rows[1]).toHaveTextContent("Empty Account");
      expect(rows[2]).toHaveTextContent("Brokerage Account");
      expect(rows[3]).toHaveTextContent("Retirement Account");
    });

    it("sorts by status correctly", () => {
      renderAccountList({
        accounts: baseAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const statusHeader = screen.getByText("Status");
      fireEvent.click(statusHeader);

      const rows = screen.getAllByRole("row");
      expect(rows[1]).toHaveTextContent("Empty Account");
    });
  });

  describe("filtering", () => {
    it("hides inactive accounts when hideInactive is true", () => {
      renderAccountList({
        accounts: baseAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
        hideInactive: true,
      });

      expect(screen.queryByText("Empty Account")).not.toBeInTheDocument();
      expect(screen.getByText("Brokerage Account")).toBeInTheDocument();
      expect(screen.getByText("Retirement Account")).toBeInTheDocument();
    });

    it("shows all accounts when hideInactive is false", () => {
      renderAccountList({
        accounts: baseAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
        hideInactive: false,
      });

      expect(screen.getByText("Empty Account")).toBeInTheDocument();
      expect(screen.getByText("Brokerage Account")).toBeInTheDocument();
      expect(screen.getByText("Retirement Account")).toBeInTheDocument();
    });
  });

  describe("sync status icons", () => {
    it("shows green check for stale accounts with recent balance_date", () => {
      const accountsWithStale: Account[] = [
        {
          ...baseAccounts[0],
          last_sync_status: "stale",
          balance_date: new Date().toISOString(),
        },
      ];

      renderAccountList({
        accounts: accountsWithStale,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const okIcon = screen.getByTestId("sync-ok-acc-1");
      expect(okIcon).toBeInTheDocument();
      expect(okIcon).toHaveClass("text-tf-positive");
    });

    it("shows yellow warning icon for stale accounts with old balance_date", () => {
      const oldDate = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
      const accountsWithStale: Account[] = [
        {
          ...baseAccounts[0],
          last_sync_status: "stale",
          balance_date: oldDate,
        },
      ];

      renderAccountList({
        accounts: accountsWithStale,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const warning = screen.getByTestId("sync-warning-acc-1");
      expect(warning).toBeInTheDocument();
      expect(warning).toHaveClass("text-tf-warning");
    });

    it("shows red error icon for error accounts with error message in tooltip", () => {
      const accountsWithError: Account[] = [
        {
          ...baseAccounts[0],
          last_sync_status: "error",
          last_sync_error: "Connection to Vanguard may need attention",
        },
      ];

      renderAccountList({
        accounts: accountsWithError,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const errorIcon = screen.getByTestId("sync-error-acc-1");
      expect(errorIcon).toBeInTheDocument();
      expect(errorIcon).toHaveClass("text-tf-negative");
      // Tooltip includes error message
      const titleEl = errorIcon.querySelector("title");
      expect(titleEl?.textContent).toContain("Connection to Vanguard may need attention");
    });

    it("does not show warning or error icon for success accounts", () => {
      const recentAccount: Account[] = [
        {
          ...baseAccounts[0],
          last_sync_time: new Date().toISOString(),
          last_sync_status: "success",
        },
      ];

      renderAccountList({
        accounts: recentAccount,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      expect(screen.queryByTestId("sync-warning-acc-1")).not.toBeInTheDocument();
      expect(screen.queryByTestId("sync-error-acc-1")).not.toBeInTheDocument();
      expect(screen.getByTestId("sync-ok-acc-1")).toBeInTheDocument();
    });

    it("shows yellow warning icon for skipped accounts", () => {
      const accountsWithSkipped: Account[] = [
        {
          ...baseAccounts[0],
          last_sync_status: "skipped",
          last_sync_error: "Account not returned by provider — connection may need attention",
        },
      ];

      renderAccountList({
        accounts: accountsWithSkipped,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const warning = screen.getByTestId("sync-warning-acc-1");
      expect(warning).toBeInTheDocument();
      const titleEl = warning.querySelector("title");
      expect(titleEl?.textContent).toContain("Account not returned by provider — connection may need attention");
    });

    it("shows yellow warning for accounts not synced within 7 days", () => {
      const oldSyncTime = new Date(Date.now() - 8 * 24 * 60 * 60 * 1000).toISOString();
      const staleAccounts: Account[] = [
        {
          ...baseAccounts[0],
          last_sync_time: oldSyncTime,
          last_sync_status: "success",
        },
      ];

      renderAccountList({
        accounts: staleAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      expect(screen.getByTestId("sync-warning-acc-1")).toBeInTheDocument();
    });

    it("shows green check for recently synced accounts", () => {
      const recentAccounts: Account[] = [
        {
          ...baseAccounts[0],
          last_sync_time: new Date().toISOString(),
          last_sync_status: "success",
        },
      ];

      renderAccountList({
        accounts: recentAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const okIcon = screen.getByTestId("sync-ok-acc-1");
      expect(okIcon).toBeInTheDocument();
      expect(okIcon).toHaveClass("text-tf-positive");
    });

    it("shows green pin icon for manual accounts", () => {
      const manualAccounts: Account[] = [
        {
          ...baseAccounts[0],
          id: "acc-manual",
          provider_name: "Manual",
          last_sync_time: null,
          last_sync_status: null,
          balance_date: "2026-01-15T00:00:00Z",
        },
      ];

      renderAccountList({
        accounts: manualAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const pencilIcon = screen.getByTestId("sync-manual-acc-manual");
      expect(pencilIcon).toBeInTheDocument();
      expect(pencilIcon).toHaveClass("text-tf-positive");
      const titleEl = pencilIcon.querySelector("title");
      expect(titleEl?.textContent).toContain("Manual account");
      expect(titleEl?.textContent).toContain("Last updated:");
    });
  });

  describe("column resizing", () => {
    it("has resize handles on column headers", () => {
      renderAccountList({
        accounts: baseAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const resizeHandles = document.querySelectorAll(".cursor-col-resize");
      expect(resizeHandles.length).toBeGreaterThan(0);
    });
  });

  describe("scroll preservation", () => {
    it("has a scrollable container", () => {
      renderAccountList({
        accounts: baseAccounts,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const container = screen.getByTestId("account-list-container");
      expect(container).toHaveClass("overflow-auto");
    });
  });

  describe("manual account differentiation", () => {
    const accountsWithManual: Account[] = [
      ...baseAccounts,
      {
        id: "acc-manual",
        name: "My House",
        provider_name: "Manual",
        institution_name: null,
        external_id: "uuid-manual",
        is_active: true,
        account_type: null,
        include_in_allocation: true,
        assigned_asset_class_id: null,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
        value: "500000.00",
        last_sync_time: null,
        last_sync_status: null,
        balance_date: null,
      },
    ];

    it("shows Manual badge for manual accounts", () => {
      renderAccountList({
        accounts: accountsWithManual,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      expect(screen.getByTestId("manual-badge-acc-manual")).toBeInTheDocument();
      expect(screen.getByTestId("manual-badge-acc-manual")).toHaveTextContent("Manual");
    });

    it("does not show Manual badge for non-manual accounts", () => {
      renderAccountList({
        accounts: accountsWithManual,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      expect(screen.queryByTestId("manual-badge-acc-1")).not.toBeInTheDocument();
      expect(screen.queryByTestId("manual-badge-acc-2")).not.toBeInTheDocument();
    });

    it("shows pin icon for manual accounts", () => {
      renderAccountList({
        accounts: accountsWithManual,
        loading: false,
        onEdit: mockEdit,
        onToggleActive: mockToggleActive,
        onDelete: mockDelete,
      });

      const pencilIcon = screen.getByTestId("sync-manual-acc-manual");
      expect(pencilIcon).toBeInTheDocument();
      expect(pencilIcon).toHaveClass("text-tf-positive");
    });
  });
});
