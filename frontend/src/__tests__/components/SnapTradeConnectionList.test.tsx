import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SnapTradeConnectionList } from "../../components/settings/SnapTradeConnectionList";

vi.mock("../../api/snaptrade", () => ({
  snaptradeApi: {
    listConnections: vi.fn(),
    getConnectUrl: vi.fn(),
    removeConnection: vi.fn(),
    refreshConnection: vi.fn(),
  },
}));

import { snaptradeApi } from "../../api/snaptrade";

const mockedListConnections = vi.mocked(snaptradeApi.listConnections);
const mockedGetConnectUrl = vi.mocked(snaptradeApi.getConnectUrl);
const mockedRemoveConnection = vi.mocked(snaptradeApi.removeConnection);
const mockedRefreshConnection = vi.mocked(snaptradeApi.refreshConnection);

const mockConnections = [
  {
    authorization_id: "auth-1",
    brokerage_name: "Alpaca",
    name: "My Alpaca",
    disabled: false,
    disabled_date: null,
    error_message: null,
  },
  {
    authorization_id: "auth-2",
    brokerage_name: "Questrade",
    name: "Questrade TFSA",
    disabled: true,
    disabled_date: "2026-01-15",
    error_message: "Token expired",
  },
];

describe("SnapTradeConnectionList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedListConnections.mockResolvedValue({ data: mockConnections } as never);
  });

  it("renders connections after loading", async () => {
    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(screen.getByText("My Alpaca")).toBeInTheDocument();
    });

    expect(screen.getByText("Questrade TFSA")).toBeInTheDocument();
    expect(screen.getByText("Brokerage Connections")).toBeInTheDocument();
  });

  it("shows loading state initially", () => {
    mockedListConnections.mockReturnValue(new Promise(() => {}) as never);

    render(<SnapTradeConnectionList />);

    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows empty state when no connections", async () => {
    mockedListConnections.mockResolvedValue({ data: [] } as never);

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(
        screen.getByText(/No brokerage connections yet/),
      ).toBeInTheDocument();
    });
  });

  it("shows fetch error state", async () => {
    mockedListConnections.mockRejectedValue(new Error("Network error"));

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to load brokerage connections."),
      ).toBeInTheDocument();
    });
  });

  it("shows disabled connection status", async () => {
    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(screen.getByText("Token expired")).toBeInTheDocument();
    });
  });

  it("shows Add Connection button", async () => {
    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Add Connection" }),
      ).toBeInTheDocument();
    });
  });

  it("handles Add Connection flow", async () => {
    const mockOpen = vi.fn().mockReturnValue({ location: {} });
    vi.stubGlobal("open", mockOpen);

    mockedGetConnectUrl.mockResolvedValue({
      data: { redirect_url: "https://app.snaptrade.com/connect?token=abc" },
    } as never);

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Add Connection" }),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Add Connection" }));

    await waitFor(() => {
      expect(mockedGetConnectUrl).toHaveBeenCalled();
    });

    expect(mockOpen).toHaveBeenCalledWith("about:blank", "_blank");
  });

  it("shows error when popup is blocked", async () => {
    vi.stubGlobal("open", vi.fn().mockReturnValue(null));

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Add Connection" }),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Add Connection" }));

    await waitFor(() => {
      expect(screen.getByText(/Popup blocked/)).toBeInTheDocument();
    });

    expect(mockedGetConnectUrl).not.toHaveBeenCalled();
  });

  it("shows error when Add Connection fails", async () => {
    const mockOpen = vi.fn().mockReturnValue({ close: vi.fn() });
    vi.stubGlobal("open", mockOpen);

    mockedGetConnectUrl.mockRejectedValue(new Error("Failed"));

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Add Connection" }),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Add Connection" }));

    await waitFor(() => {
      expect(
        screen.getByText("Failed to generate connection URL."),
      ).toBeInTheDocument();
    });
  });

  it("handles Remove connection flow", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockedRemoveConnection.mockResolvedValue({ data: { status: "ok" } } as never);

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(screen.getByText("My Alpaca")).toBeInTheDocument();
    });

    const removeButton = screen.getByRole("button", { name: "Remove My Alpaca" });
    fireEvent.click(removeButton);

    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining("Remove My Alpaca"),
    );

    await waitFor(() => {
      expect(mockedRemoveConnection).toHaveBeenCalledWith("auth-1");
    });

    // Connection should be removed from the list
    await waitFor(() => {
      expect(screen.queryByText("My Alpaca")).not.toBeInTheDocument();
    });
  });

  it("does nothing when Remove is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(screen.getByText("My Alpaca")).toBeInTheDocument();
    });

    const removeButton = screen.getByRole("button", { name: "Remove My Alpaca" });
    fireEvent.click(removeButton);

    expect(mockedRemoveConnection).not.toHaveBeenCalled();
  });

  it("shows error when Remove fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockedRemoveConnection.mockRejectedValue(new Error("Server error"));

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(screen.getByText("My Alpaca")).toBeInTheDocument();
    });

    const removeButton = screen.getByRole("button", { name: "Remove My Alpaca" });
    fireEvent.click(removeButton);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to remove connection. Please try again."),
      ).toBeInTheDocument();
    });
  });

  it("handles Update (reconnect) flow by opening new tab", async () => {
    const mockOpen = vi.fn().mockReturnValue({ location: {} });
    vi.stubGlobal("open", mockOpen);

    mockedRefreshConnection.mockResolvedValue({
      data: {
        redirect_url: "https://app.snaptrade.com/reconnect?token=xyz",
        authorization_id: "auth-1",
      },
    } as never);

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(screen.getByText("My Alpaca")).toBeInTheDocument();
    });

    const updateButton = screen.getByRole("button", { name: "Update My Alpaca" });
    fireEvent.click(updateButton);

    await waitFor(() => {
      expect(mockedRefreshConnection).toHaveBeenCalledWith("auth-1");
    });

    expect(mockOpen).toHaveBeenCalledWith("about:blank", "_blank");
  });

  it("shows error when Update fails", async () => {
    const mockOpen = vi.fn().mockReturnValue({ close: vi.fn() });
    vi.stubGlobal("open", mockOpen);

    mockedRefreshConnection.mockRejectedValue(new Error("Server error"));

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(screen.getByText("My Alpaca")).toBeInTheDocument();
    });

    const updateButton = screen.getByRole("button", { name: "Update My Alpaca" });
    fireEvent.click(updateButton);

    await waitFor(() => {
      expect(
        screen.getByText(
          "Failed to generate reconnect URL. Please try again.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("shows error when Update popup is blocked", async () => {
    vi.stubGlobal("open", vi.fn().mockReturnValue(null));

    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(screen.getByText("My Alpaca")).toBeInTheDocument();
    });

    const updateButton = screen.getByRole("button", { name: "Update My Alpaca" });
    fireEvent.click(updateButton);

    await waitFor(() => {
      expect(screen.getByText(/Popup blocked/)).toBeInTheDocument();
    });

    expect(mockedRefreshConnection).not.toHaveBeenCalled();
  });

  it("shows brokerage name as subtitle when different from name", async () => {
    render(<SnapTradeConnectionList />);

    await waitFor(() => {
      expect(screen.getByText("My Alpaca")).toBeInTheDocument();
    });

    // "Alpaca" is brokerage_name and differs from name "My Alpaca"
    expect(screen.getByText("Alpaca")).toBeInTheDocument();
  });
});
