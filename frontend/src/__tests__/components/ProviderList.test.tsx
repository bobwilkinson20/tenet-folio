import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ProviderList } from "../../components/settings/ProviderList";

const mockProviders = [
  {
    name: "SnapTrade",
    has_credentials: true,
    is_enabled: true,
    account_count: 2,
    last_sync_time: "2026-01-15T10:00:00Z",
    supports_setup: false,
  },
  {
    name: "SimpleFIN",
    has_credentials: true,
    is_enabled: false,
    account_count: 1,
    last_sync_time: null,
    supports_setup: true,
  },
  {
    name: "IBKR",
    has_credentials: false,
    is_enabled: true,
    account_count: 0,
    last_sync_time: null,
    supports_setup: true,
  },
  {
    name: "Coinbase",
    has_credentials: true,
    is_enabled: true,
    account_count: 1,
    last_sync_time: "2026-01-10T09:00:00Z",
    supports_setup: true,
  },
  {
    name: "Schwab",
    has_credentials: false,
    is_enabled: true,
    account_count: 0,
    last_sync_time: null,
    supports_setup: true,
  },
];

vi.mock("../../api", () => ({
  providersApi: {
    list: vi.fn(),
    update: vi.fn(),
    getSetupInfo: vi.fn(),
    setup: vi.fn(),
    removeCredentials: vi.fn(),
  },
}));

vi.mock("../../api/schwab", () => ({
  schwabApi: {
    getTokenStatus: vi.fn().mockResolvedValue({
      data: { status: "no_credentials", message: "", days_remaining: null },
    }),
    createAuthUrl: vi.fn(),
    exchangeToken: vi.fn(),
  },
}));

import { providersApi } from "../../api";

const mockedList = vi.mocked(providersApi.list);
const mockedUpdate = vi.mocked(providersApi.update);
const mockedRemoveCredentials = vi.mocked(providersApi.removeCredentials);

describe("ProviderList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedList.mockResolvedValue({ data: mockProviders } as never);
  });

  it("renders all providers", async () => {
    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SnapTrade")).toBeInTheDocument();
    });

    expect(screen.getByText("SimpleFIN")).toBeInTheDocument();
    expect(screen.getByText("IBKR")).toBeInTheDocument();
    expect(screen.getByText("Coinbase")).toBeInTheDocument();
    expect(screen.getByText("Schwab")).toBeInTheDocument();
  });

  it("shows Configured badge for providers with credentials", async () => {
    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SnapTrade")).toBeInTheDocument();
    });

    const configuredBadges = screen.getAllByText("Configured");
    const notConfiguredBadges = screen.getAllByText("Not Configured");

    // SnapTrade, SimpleFIN, Coinbase have credentials
    expect(configuredBadges).toHaveLength(3);
    // IBKR, Schwab don't
    expect(notConfiguredBadges).toHaveLength(2);
  });

  it("shows account count for providers with accounts", async () => {
    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SnapTrade")).toBeInTheDocument();
    });

    expect(screen.getByText("2 accounts")).toBeInTheDocument();
    // SimpleFIN and Coinbase both have 1 account
    expect(screen.getAllByText("1 account")).toHaveLength(2);
  });

  it("disables toggle for unconfigured providers", async () => {
    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("IBKR")).toBeInTheDocument();
    });

    const toggles = screen.getAllByRole("checkbox");
    // IBKR (index 2) should be disabled (no credentials)
    expect(toggles[2]).toBeDisabled();
    // Schwab (index 4) should be disabled (no credentials)
    expect(toggles[4]).toBeDisabled();
    // SnapTrade (index 0) should be enabled
    expect(toggles[0]).not.toBeDisabled();
  });

  it("calls update API when toggling a provider", async () => {
    mockedUpdate.mockResolvedValue({
      data: { ...mockProviders[0], is_enabled: false },
    } as never);

    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SnapTrade")).toBeInTheDocument();
    });

    const toggles = screen.getAllByRole("checkbox");
    fireEvent.click(toggles[0]); // Toggle SnapTrade

    await waitFor(() => {
      expect(mockedUpdate).toHaveBeenCalledWith("SnapTrade", false);
    });
  });

  it("shows loading state", () => {
    mockedList.mockReturnValue(new Promise(() => {}) as never);

    render(<ProviderList />);

    expect(screen.getByText("Loading providers...")).toBeInTheDocument();
  });

  it("shows error state", async () => {
    mockedList.mockRejectedValue(new Error("Network error"));

    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load providers")).toBeInTheDocument();
    });
  });

  it("rolls back on update failure", async () => {
    mockedUpdate.mockRejectedValue(new Error("Server error"));

    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SnapTrade")).toBeInTheDocument();
    });

    const toggles = screen.getAllByRole("checkbox");
    // SnapTrade starts enabled
    expect(toggles[0]).toBeChecked();

    fireEvent.click(toggles[0]);

    // After error, should roll back to checked
    await waitFor(() => {
      expect(toggles[0]).toBeChecked();
    });
  });

  it("shows Reconfigure button for configured providers with setup support", async () => {
    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SimpleFIN")).toBeInTheDocument();
    });

    // SimpleFIN and Coinbase have credentials + supports_setup → Reconfigure + Remove each
    expect(screen.getAllByRole("button", { name: "Reconfigure" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(2);
  });

  it("shows Configure button for unconfigured SimpleFIN", async () => {
    const providersWithoutSimpleFIN = mockProviders.map((p) =>
      p.name === "SimpleFIN" ? { ...p, has_credentials: false } : p,
    );
    mockedList.mockResolvedValue({ data: providersWithoutSimpleFIN } as never);

    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SimpleFIN")).toBeInTheDocument();
    });

    // SimpleFIN, IBKR, and Schwab show Configure (all unconfigured with supports_setup)
    expect(screen.getAllByRole("button", { name: "Configure" })).toHaveLength(3);
  });

  it("does not show setup buttons for non-setup providers", async () => {
    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SnapTrade")).toBeInTheDocument();
    });

    // SnapTrade has credentials but no in-app setup → no Configure/Reconfigure
    // SimpleFIN and Coinbase have credentials + supports_setup → Reconfigure/Remove
    expect(screen.getAllByRole("button", { name: "Reconfigure" })).toHaveLength(2);
    // IBKR and Schwab have supports_setup but no credentials → Configure button
    expect(screen.getAllByRole("button", { name: "Configure" })).toHaveLength(2);
  });

  it("clicking Remove calls removeCredentials after confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockedRemoveCredentials.mockResolvedValue({ data: { provider: "SimpleFIN", message: "removed" } } as never);

    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SimpleFIN")).toBeInTheDocument();
    });

    const simplefinRow = screen.getByTestId("provider-row-SimpleFIN");
    fireEvent.click(within(simplefinRow).getByRole("button", { name: "Remove" }));

    expect(window.confirm).toHaveBeenCalledWith("Remove credentials for SimpleFIN?");
    await waitFor(() => {
      expect(mockedRemoveCredentials).toHaveBeenCalledWith("SimpleFIN");
    });
  });

  it("clicking Remove does nothing when confirm is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SimpleFIN")).toBeInTheDocument();
    });

    const simplefinRow = screen.getByTestId("provider-row-SimpleFIN");
    fireEvent.click(within(simplefinRow).getByRole("button", { name: "Remove" }));

    expect(window.confirm).toHaveBeenCalled();
    expect(mockedRemoveCredentials).not.toHaveBeenCalled();
  });

  it("shows error when removeCredentials fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockedRemoveCredentials.mockRejectedValue({
      response: { data: { detail: "Keychain unavailable" } },
    });

    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SimpleFIN")).toBeInTheDocument();
    });

    const simplefinRow = screen.getByTestId("provider-row-SimpleFIN");
    fireEvent.click(within(simplefinRow).getByRole("button", { name: "Remove" }));

    await waitFor(() => {
      expect(screen.getByText("Keychain unavailable")).toBeInTheDocument();
    });
  });

  it("clicking Configure opens setup dialog", async () => {
    const providersWithoutSimpleFIN = mockProviders.map((p) =>
      p.name === "SimpleFIN" ? { ...p, has_credentials: false } : p,
    );
    mockedList.mockResolvedValue({ data: providersWithoutSimpleFIN } as never);
    vi.mocked(providersApi.getSetupInfo).mockResolvedValue({
      data: [
        {
          key: "setup_token",
          label: "Setup Token",
          help_text: "Paste token",
          input_type: "password",
        },
      ],
    } as never);

    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SimpleFIN")).toBeInTheDocument();
    });

    const simplefinRow = screen.getByTestId("provider-row-SimpleFIN");
    fireEvent.click(within(simplefinRow).getByRole("button", { name: "Configure" }));

    await waitFor(() => {
      expect(screen.getByText("Configure SimpleFIN")).toBeInTheDocument();
    });
  });

  it("shows Configure button for IBKR with supports_setup", async () => {
    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("IBKR")).toBeInTheDocument();
    });

    // IBKR and Schwab both have supports_setup=true but no credentials → Configure button
    expect(screen.getAllByRole("button", { name: "Configure" })).toHaveLength(2);
  });
});
