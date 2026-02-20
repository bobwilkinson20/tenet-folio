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
  },
  {
    name: "SimpleFIN",
    has_credentials: true,
    is_enabled: false,
    account_count: 1,
    last_sync_time: null,
  },
  {
    name: "IBKR",
    has_credentials: false,
    is_enabled: true,
    account_count: 0,
    last_sync_time: null,
  },
  {
    name: "Coinbase",
    has_credentials: true,
    is_enabled: true,
    account_count: 1,
    last_sync_time: "2026-01-10T09:00:00Z",
  },
  {
    name: "Schwab",
    has_credentials: false,
    is_enabled: true,
    account_count: 0,
    last_sync_time: null,
  },
];

vi.mock("../../api", () => ({
  providersApi: {
    list: vi.fn(),
    update: vi.fn(),
  },
}));

import { providersApi } from "../../api";

const mockedList = vi.mocked(providersApi.list);
const mockedUpdate = vi.mocked(providersApi.update);

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
});
