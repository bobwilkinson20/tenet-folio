import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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
    supports_setup: false,
  },
  {
    name: "Coinbase",
    has_credentials: true,
    is_enabled: true,
    account_count: 1,
    last_sync_time: "2026-01-10T09:00:00Z",
    supports_setup: false,
  },
  {
    name: "Schwab",
    has_credentials: false,
    is_enabled: true,
    account_count: 0,
    last_sync_time: null,
    supports_setup: false,
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
    // IBKR (index 2) and Schwab (index 4) should be disabled
    expect(toggles[2]).toBeDisabled();
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

  it("shows Reconfigure button for configured SimpleFIN", async () => {
    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SimpleFIN")).toBeInTheDocument();
    });

    // SimpleFIN has credentials → Reconfigure + Remove
    expect(screen.getByRole("button", { name: "Reconfigure" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
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

    expect(screen.getByRole("button", { name: "Configure" })).toBeInTheDocument();
  });

  it("does not show setup buttons for non-setup providers", async () => {
    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SnapTrade")).toBeInTheDocument();
    });

    // SnapTrade has credentials but no in-app setup → no Configure/Reconfigure
    // Only SimpleFIN should have Reconfigure/Remove, not SnapTrade/Coinbase
    expect(screen.getAllByRole("button", { name: "Reconfigure" })).toHaveLength(1);
  });

  it("clicking Remove calls removeCredentials after confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockedRemoveCredentials.mockResolvedValue({ data: { provider: "SimpleFIN", message: "removed" } } as never);

    render(<ProviderList />);

    await waitFor(() => {
      expect(screen.getByText("SimpleFIN")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

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

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

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

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

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

    fireEvent.click(screen.getByRole("button", { name: "Configure" }));

    await waitFor(() => {
      expect(screen.getByText("Configure SimpleFIN")).toBeInTheDocument();
    });
  });
});
