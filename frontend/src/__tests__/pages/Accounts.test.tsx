import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AccountsPage } from "../../pages/Accounts";
import { usePreferences } from "../../hooks";

// Stateful mock for usePreferences
const mockSetPreference = vi.fn();

// Mock the hooks
vi.mock("../../hooks", () => ({
  useAccounts: vi.fn(() => ({
    accounts: [
      {
        id: "acc-1",
        name: "Active Account",
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
      },
      {
        id: "acc-2",
        name: "Inactive Account",
        provider_name: "SimpleFIN",
        institution_name: null,
        external_id: "ext-2",
        is_active: false,
        account_type: null,
        include_in_allocation: true,
        assigned_asset_class_id: null,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
        value: "25000.00",
      },
    ],
    loading: false,
    refetch: vi.fn(),
    updateAccount: vi.fn(),
    deleteAccount: vi.fn(),
  })),
  usePreferences: vi.fn(),
}));

// Mock the API modules
vi.mock("../../api/assetTypes", () => ({
  assetTypeApi: {
    list: vi.fn().mockResolvedValue({ data: { items: [] } }),
  },
}));

vi.mock("../../api/accounts", () => ({
  accountsApi: {
    update: vi.fn().mockResolvedValue({ data: {} }),
    createManual: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

vi.mock("../../api", () => ({
  accountsApi: {
    update: vi.fn().mockResolvedValue({ data: {} }),
  },
  syncApi: {
    trigger: vi.fn().mockResolvedValue({
      data: { sync_log: [{ id: "1", provider_name: "SnapTrade", status: "success", accounts_synced: 2 }] },
    }),
  },
}));

async function renderAccountsPage() {
  const result = render(<MemoryRouter><AccountsPage /></MemoryRouter>);
  // Wait for AccountList's useEffect async operations to settle
  await act(async () => {});
  return result;
}

describe("AccountsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(usePreferences).mockReturnValue({
      loading: false,
      getPreference: <T,>(_key: string, defaultValue: T): T => defaultValue,
      setPreference: mockSetPreference,
    });
  });

  it("renders the hide inactive toggle", async () => {
    await renderAccountsPage();

    expect(screen.getByText("Hide inactive accounts")).toBeInTheDocument();
    expect(screen.getByTestId("hide-inactive-toggle")).toBeInTheDocument();
  });

  it("shows all accounts by default", async () => {
    await renderAccountsPage();

    expect(screen.getByText("Active Account")).toBeInTheDocument();
    expect(screen.getByText("Inactive Account")).toBeInTheDocument();
  });

  it("calls setPreference when toggle is checked", async () => {
    await renderAccountsPage();

    const toggle = screen.getByTestId("hide-inactive-toggle");
    fireEvent.click(toggle);

    expect(mockSetPreference).toHaveBeenCalledWith("accounts.hideInactive", true);
  });

  it("hides inactive accounts when preference is true", async () => {
    vi.mocked(usePreferences).mockReturnValue({
      loading: false,
      getPreference: <T,>(key: string, defaultValue: T): T =>
        key === "accounts.hideInactive" ? (true as T) : defaultValue,
      setPreference: mockSetPreference,
    });

    await renderAccountsPage();

    expect(screen.getByText("Active Account")).toBeInTheDocument();
    expect(screen.queryByText("Inactive Account")).not.toBeInTheDocument();
  });

  it("shows inactive accounts when preference is false", async () => {
    await renderAccountsPage();

    expect(screen.getByText("Active Account")).toBeInTheDocument();
    expect(screen.getByText("Inactive Account")).toBeInTheDocument();
  });

  it("renders the sync button", async () => {
    await renderAccountsPage();

    expect(screen.getByText("Sync Now")).toBeInTheDocument();
  });

  it("renders the Add Manual Account button", async () => {
    await renderAccountsPage();

    expect(screen.getByTestId("add-manual-account-button")).toBeInTheDocument();
    expect(screen.getByText("Add Manual Account")).toBeInTheDocument();
  });

  it("opens manual account modal when button is clicked", async () => {
    await renderAccountsPage();

    fireEvent.click(screen.getByTestId("add-manual-account-button"));

    await waitFor(() => {
      expect(screen.getByText("Add Manual Account", { selector: "h3" })).toBeInTheDocument();
      expect(screen.getByTestId("manual-account-name")).toBeInTheDocument();
    });
  });
});
