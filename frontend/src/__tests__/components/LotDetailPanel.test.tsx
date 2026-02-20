import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { LotDetailPanel } from "../../components/lots/LotDetailPanel";

vi.mock("../../api/accounts", () => ({
  accountsApi: {
    getLotsBySecurity: vi.fn(),
    createLot: vi.fn(),
    updateLot: vi.fn(),
    deleteLot: vi.fn(),
  },
}));

import { accountsApi } from "../../api/accounts";

const mockOpenLot = {
  id: "lot-1",
  account_id: "acc-1",
  security_id: "sec-1",
  ticker: "AAPL",
  acquisition_date: "2025-01-15",
  cost_basis_per_unit: 150,
  original_quantity: 10,
  current_quantity: 10,
  is_closed: false,
  source: "manual" as const,
  activity_id: null,
  total_cost_basis: 1500,
  unrealized_gain_loss: 250,
  unrealized_gain_loss_percent: 16.67,
  security_name: "Apple Inc.",
  disposals: [],
  created_at: "2025-01-15T00:00:00Z",
  updated_at: "2025-01-15T00:00:00Z",
};

const mockClosedLot = {
  ...mockOpenLot,
  id: "lot-2",
  current_quantity: 0,
  is_closed: true,
  source: "inferred" as const,
};

describe("LotDetailPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders open lots", async () => {
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: [mockOpenLot],
    } as never);

    render(
      <LotDetailPanel
        accountId="acc-1"
        securityId="sec-1"
        ticker="AAPL"
        marketPrice={175}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("2025-01-15")).toBeInTheDocument();
    });

    expect(screen.getByTestId("lot-detail-panel")).toBeInTheDocument();
    expect(screen.getByTestId("open-lots-table")).toBeInTheDocument();
    expect(screen.getByText("Manual")).toBeInTheDocument();
    expect(screen.getByTestId("add-lot-button")).toBeInTheDocument();
  });

  it("shows empty state when no lots", async () => {
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: [],
    } as never);

    render(
      <LotDetailPanel
        accountId="acc-1"
        securityId="sec-1"
        ticker="AAPL"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/No open lots/)).toBeInTheDocument();
    });
  });

  it("shows edit/delete for manual lots", async () => {
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: [mockOpenLot],
    } as never);

    render(
      <LotDetailPanel
        accountId="acc-1"
        securityId="sec-1"
        ticker="AAPL"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("edit-lot-lot-1")).toBeInTheDocument();
    });

    expect(screen.getByTestId("delete-lot-lot-1")).toBeInTheDocument();
  });

  it("hides edit/delete for activity lots", async () => {
    const activityLot = { ...mockOpenLot, source: "activity" as const };
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: [activityLot],
    } as never);

    render(
      <LotDetailPanel
        accountId="acc-1"
        securityId="sec-1"
        ticker="AAPL"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Activity")).toBeInTheDocument();
    });

    expect(screen.queryByTestId("edit-lot-lot-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("delete-lot-lot-1")).not.toBeInTheDocument();
  });

  it("toggles closed lots visibility", async () => {
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: [mockOpenLot, mockClosedLot],
    } as never);

    render(
      <LotDetailPanel
        accountId="acc-1"
        securityId="sec-1"
        ticker="AAPL"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("toggle-closed-lots")).toBeInTheDocument();
    });

    // Closed lots table should not be visible initially
    expect(screen.queryByTestId("closed-lots-table")).not.toBeInTheDocument();

    // Click to show
    fireEvent.click(screen.getByTestId("toggle-closed-lots"));
    expect(screen.getByTestId("closed-lots-table")).toBeInTheDocument();

    // Click to hide
    fireEvent.click(screen.getByTestId("toggle-closed-lots"));
    expect(screen.queryByTestId("closed-lots-table")).not.toBeInTheDocument();
  });

  it("calls deleteLot when delete confirmed", async () => {
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: [mockOpenLot],
    } as never);
    vi.mocked(accountsApi.deleteLot).mockResolvedValue({} as never);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(
      <LotDetailPanel
        accountId="acc-1"
        securityId="sec-1"
        ticker="AAPL"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("delete-lot-lot-1")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("delete-lot-lot-1"));

    await waitFor(() => {
      expect(accountsApi.deleteLot).toHaveBeenCalledWith("acc-1", "lot-1");
    });

    vi.mocked(window.confirm).mockRestore();
  });
});
