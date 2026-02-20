import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AccountDetailsPage } from "../../pages/AccountDetails";

vi.mock("../../api/accounts", () => ({
  accountsApi: {
    get: vi.fn(),
    getHoldings: vi.fn(),
    getActivities: vi.fn(),
    addHolding: vi.fn(),
    updateHolding: vi.fn(),
    deleteHolding: vi.fn(),
  },
}));

import { accountsApi } from "../../api/accounts";

const mockAccount = {
  id: "acc-1",
  name: "Test Brokerage",
  provider_name: "SnapTrade",
  institution_name: "Vanguard",
  external_id: "ext-1",
  is_active: true,
  assigned_asset_class_id: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  value: "50000.00",
  last_sync_time: null,
  last_sync_status: null,
  balance_date: null,
};

const mockHoldings = [
  {
    id: "h-1",
    account_snapshot_id: "acct-snap-1",
    ticker: "VTI",
    security_name: "Vanguard Total Stock Market ETF",
    quantity: "100",
    snapshot_price: "250.00",
    snapshot_value: "25000.00",
    market_price: "260.00",
    market_value: "26000.00",
    created_at: "2025-06-01T00:00:00Z",
  },
];

const mockActivities = [
  {
    id: "act-1",
    account_id: "acc-1",
    provider_name: "SnapTrade",
    external_id: "ext-act-1",
    activity_date: "2025-06-15T00:00:00Z",
    settlement_date: null,
    type: "DIVIDEND",
    description: "Quarterly dividend",
    ticker: "VTI",
    units: null,
    price: null,
    amount: "125.50",
    currency: "USD",
    fee: null,
    created_at: "2025-06-15T12:00:00Z",
  },
  {
    id: "act-2",
    account_id: "acc-1",
    provider_name: "SnapTrade",
    external_id: "ext-act-2",
    activity_date: "2025-06-10T00:00:00Z",
    settlement_date: null,
    type: "BUY",
    description: "Purchased shares",
    ticker: "VTI",
    units: "10",
    price: "245.00",
    amount: "-2450.00",
    currency: "USD",
    fee: "0",
    created_at: "2025-06-10T12:00:00Z",
  },
];

function renderAccountDetails(id = "acc-1") {
  return render(
    <MemoryRouter initialEntries={[`/accounts/${id}`]}>
      <Routes>
        <Route path="/accounts/:id" element={<AccountDetailsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AccountDetailsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading state initially", () => {
    vi.mocked(accountsApi.get).mockReturnValue(new Promise(() => {}) as never);
    vi.mocked(accountsApi.getHoldings).mockReturnValue(new Promise(() => {}) as never);
    vi.mocked(accountsApi.getActivities).mockReturnValue(new Promise(() => {}) as never);

    renderAccountDetails();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders account details with holdings and activities", async () => {
    vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
    vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockHoldings } as never);
    vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: mockActivities } as never);

    renderAccountDetails();

    await waitFor(() => {
      expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
    });

    // Holdings
    expect(screen.getByText("VTI")).toBeInTheDocument();

    // Activity section heading
    expect(screen.getByText("Activity")).toBeInTheDocument();

    // Activity data
    expect(screen.getByText("Dividend")).toBeInTheDocument();
    expect(screen.getByText("Quarterly dividend")).toBeInTheDocument();
    expect(screen.getByText("Buy")).toBeInTheDocument();
    expect(screen.getByText("Purchased shares")).toBeInTheDocument();
  });

  it("renders error state", async () => {
    vi.mocked(accountsApi.get).mockRejectedValue(new Error("Network error"));
    vi.mocked(accountsApi.getHoldings).mockRejectedValue(new Error("Network error"));
    vi.mocked(accountsApi.getActivities).mockRejectedValue(new Error("Network error"));

    renderAccountDetails();

    await waitFor(() => {
      expect(screen.getByText("Failed to load account details.")).toBeInTheDocument();
    });
  });

  it("renders empty activity state", async () => {
    vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
    vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockHoldings } as never);
    vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

    renderAccountDetails();

    await waitFor(() => {
      expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
    });

    expect(screen.getByText("No activity found.")).toBeInTheDocument();
  });

  it("fetches activities for the correct account", async () => {
    vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
    vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockHoldings } as never);
    vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

    renderAccountDetails("acc-1");

    await waitFor(() => {
      expect(accountsApi.getActivities).toHaveBeenCalledWith("acc-1");
    });
  });

  it("shows cash balance in header and hides cash from holdings table", async () => {
    const holdingsWithCash = [
      ...mockHoldings,
      {
        id: "h-cash",
        account_snapshot_id: "acct-snap-1",
        ticker: "_CASH:USD",
        security_name: "USD Cash",
        quantity: "5000.00",
        snapshot_price: "1.00",
        snapshot_value: "5000.00",
        market_price: "1.00",
        market_value: "5000.00",
        created_at: "2025-06-01T00:00:00Z",
      },
    ];

    vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
    vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: holdingsWithCash } as never);
    vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

    renderAccountDetails();

    await waitFor(() => {
      expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
    });

    // Cash should appear in header
    expect(screen.getByText(/Cash:/)).toBeInTheDocument();
    expect(screen.getByText(/\$5,000\.00/)).toBeInTheDocument();

    // Cash ticker should NOT appear in the holdings table
    expect(screen.queryByText("_CASH:USD")).not.toBeInTheDocument();

    // Regular holding should still be visible
    expect(screen.getByText("VTI")).toBeInTheDocument();
  });

  it("does not show cash line when there is no cash", async () => {
    vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
    vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockHoldings } as never);
    vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

    renderAccountDetails();

    await waitFor(() => {
      expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
    });

    // No "Cash:" text should appear
    expect(screen.queryByText(/Cash:/)).not.toBeInTheDocument();
  });

  it("uses market_value for total when available", async () => {
    vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
    vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockHoldings } as never);
    vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

    renderAccountDetails();

    await waitFor(() => {
      expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
    });

    // Should show market_value ($26,000.00) in both header total and value column,
    // not snapshot_value ($25,000.00)
    const marketValues = screen.getAllByText("$26,000.00", { exact: false });
    expect(marketValues.length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("$25,000.00", { exact: false })).not.toBeInTheDocument();
  });

  it("falls back to snapshot_value when market_value is null", async () => {
    const holdingsWithoutMarket = [
      {
        ...mockHoldings[0],
        market_price: null,
        market_value: null,
      },
    ];

    vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
    vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: holdingsWithoutMarket } as never);
    vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

    renderAccountDetails();

    await waitFor(() => {
      expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
    });

    // Should fall back to snapshot_value ($25,000.00) in both header and value column
    const snapshotValues = screen.getAllByText("$25,000.00", { exact: false });
    expect(snapshotValues.length).toBeGreaterThanOrEqual(1);
  });

  it("shows negative cash in red", async () => {
    const holdingsWithNegativeCash = [
      ...mockHoldings,
      {
        id: "h-cash",
        account_snapshot_id: "acct-snap-1",
        ticker: "_CASH:USD",
        security_name: "USD Cash",
        quantity: "-70.74",
        snapshot_price: "1.00",
        snapshot_value: "-70.74",
        market_price: "1.00",
        market_value: "-70.74",
        created_at: "2025-06-01T00:00:00Z",
      },
    ];

    vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
    vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: holdingsWithNegativeCash } as never);
    vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

    renderAccountDetails();

    await waitFor(() => {
      expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
    });

    const cashEl = screen.getByText(/Cash:/);
    expect(cashEl).toBeInTheDocument();
    expect(cashEl.className).toContain("text-tf-negative");
  });

  describe("manual account features", () => {
    const mockManualAccount = {
      ...mockAccount,
      provider_name: "Manual",
      name: "My House",
      institution_name: null,
    };

    const mockManualHoldings = [
      {
        id: "h-manual-1",
        account_snapshot_id: "acct-snap-1",
        ticker: "HOME",
        security_name: "HOME",
        quantity: "1",
        snapshot_price: "500000",
        snapshot_value: "500000",
        created_at: "2025-06-01T00:00:00Z",
      },
    ];

    it("shows Add Holding button for manual accounts", async () => {
      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockManualAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockManualHoldings } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("My House")).toBeInTheDocument();
      });

      expect(screen.getByTestId("add-holding-button")).toBeInTheDocument();
    });

    it("does not show Add Holding button for synced accounts", async () => {
      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockHoldings } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
      });

      expect(screen.queryByTestId("add-holding-button")).not.toBeInTheDocument();
    });

    it("shows edit and delete buttons in holdings table for manual accounts", async () => {
      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockManualAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockManualHoldings } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("My House")).toBeInTheDocument();
      });

      expect(screen.getByTestId("edit-holding-h-manual-1")).toBeInTheDocument();
      expect(screen.getByTestId("delete-holding-h-manual-1")).toBeInTheDocument();
    });

    it("does not show edit/delete buttons for synced accounts", async () => {
      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockHoldings } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
      });

      expect(screen.queryByTestId("edit-holding-h-1")).not.toBeInTheDocument();
      expect(screen.queryByTestId("delete-holding-h-1")).not.toBeInTheDocument();
    });

    it("calls deleteHolding API when delete is confirmed", async () => {
      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockManualAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockManualHoldings } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);
      vi.mocked(accountsApi.deleteHolding).mockResolvedValue({} as never);
      vi.spyOn(window, "confirm").mockReturnValue(true);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("My House")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId("delete-holding-h-manual-1"));

      await waitFor(() => {
        expect(accountsApi.deleteHolding).toHaveBeenCalledWith("acc-1", "h-manual-1");
      });

      vi.mocked(window.confirm).mockRestore();
    });

    it("shows appropriate empty state for manual accounts", async () => {
      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockManualAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: [] } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("My House")).toBeInTheDocument();
      });

      expect(screen.getByText("No holdings yet. Add one to get started.")).toBeInTheDocument();
    });

    it("shows sync required empty state for synced accounts", async () => {
      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: [] } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
      });

      expect(screen.getByText("No holdings found. Sync required.")).toBeInTheDocument();
    });

    it("shows description and hides ticker for _MAN: holdings", async () => {
      const manualHoldingsWithOther = [
        {
          id: "h-man-1",
          account_snapshot_id: "acct-snap-1",
          ticker: "_MAN:abc12345",
          security_name: "Primary Residence",
          quantity: "1",
          snapshot_price: "500000",
          snapshot_value: "500000",
          created_at: "2025-06-01T00:00:00Z",
        },
      ];

      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockManualAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: manualHoldingsWithOther } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("My House")).toBeInTheDocument();
      });

      // Description should be shown
      expect(screen.getByText("Primary Residence")).toBeInTheDocument();
      // Synthetic ticker should NOT be shown
      expect(screen.queryByText("_MAN:abc12345")).not.toBeInTheDocument();
    });

    it("shows description and hides ticker for _SF: holdings", async () => {
      const simplefinHoldingsWithSynthetic = [
        {
          id: "h-sf-1",
          account_snapshot_id: "acct-snap-1",
          ticker: "_SF:xyz98765",
          security_name: "Vanguard Target Trust 529",
          quantity: "100",
          snapshot_price: "150.50",
          snapshot_value: "15050",
          created_at: "2025-06-01T00:00:00Z",
        },
      ];

      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: simplefinHoldingsWithSynthetic } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
      });

      // Description should be shown
      expect(screen.getByText("Vanguard Target Trust 529")).toBeInTheDocument();
      // Synthetic ticker should NOT be shown
      expect(screen.queryByText("_SF:xyz98765")).not.toBeInTheDocument();
    });

    it("shows dash for quantity and price of _MAN: holdings", async () => {
      const manualHoldingsWithOther = [
        {
          id: "h-man-1",
          account_snapshot_id: "acct-snap-1",
          ticker: "_MAN:abc12345",
          security_name: "Primary Residence",
          quantity: "1",
          snapshot_price: "500000",
          snapshot_value: "500000",
          created_at: "2025-06-01T00:00:00Z",
        },
      ];

      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockManualAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: manualHoldingsWithOther } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("My House")).toBeInTheDocument();
      });

      // Quantity and price columns should show "-"
      const dashes = screen.getAllByText("-");
      expect(dashes.length).toBe(2);
    });
  });

  describe("cost basis columns", () => {
    const holdingsWithLots = [
      {
        id: "h-1",
        account_snapshot_id: "acct-snap-1",
        ticker: "VTI",
        security_name: "Vanguard Total Stock Market ETF",
        quantity: "100",
        snapshot_price: "250.00",
        snapshot_value: "25000.00",
        market_price: "260.00",
        market_value: "26000.00",
        created_at: "2025-06-01T00:00:00Z",
        cost_basis: "20000.00",
        gain_loss: "6000.00",
        gain_loss_percent: "0.3",
        lot_coverage: "1.0",
        lot_count: 2,
        realized_gain_loss: "0",
      },
    ];

    it("shows Cost Basis and Gain/Loss columns when holdings have lots", async () => {
      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: holdingsWithLots } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
      });

      expect(screen.getByText("Cost Basis")).toBeInTheDocument();
      expect(screen.getByText("Gain/Loss")).toBeInTheDocument();
      expect(screen.getByText("$20,000.00")).toBeInTheDocument();
      expect(screen.getByText("$6,000.00")).toBeInTheDocument();
      expect(screen.getByText("+30.0%")).toBeInTheDocument();
    });

    it("hides Cost Basis and Gain/Loss columns when no holdings have lots", async () => {
      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mockHoldings } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
      });

      expect(screen.queryByText("Cost Basis")).not.toBeInTheDocument();
      expect(screen.queryByText("Gain/Loss")).not.toBeInTheDocument();
    });

    it("shows partial lot coverage indicator", async () => {
      const holdingsPartialCoverage = [
        {
          ...holdingsWithLots[0],
          lot_coverage: "0.6",
        },
      ];

      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: holdingsPartialCoverage } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
      });

      expect(screen.getByText("~60% tracked")).toBeInTheDocument();
    });

    it("color-codes negative gain/loss in red", async () => {
      const holdingsWithLoss = [
        {
          ...holdingsWithLots[0],
          gain_loss: "-2000.00",
          gain_loss_percent: "-0.1",
        },
      ];

      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: holdingsWithLoss } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
      });

      const gainLossEl = screen.getByText("-$2,000.00");
      expect(gainLossEl.className).toContain("text-tf-negative");
      const percentEl = screen.getByText("-10.0%");
      expect(percentEl.className).toContain("text-tf-negative");
    });

    it("shows dash for holdings without lots when columns are visible", async () => {
      const mixedHoldings = [
        ...holdingsWithLots,
        {
          id: "h-2",
          account_snapshot_id: "acct-snap-1",
          ticker: "AAPL",
          security_name: "Apple Inc.",
          quantity: "50",
          snapshot_price: "180.00",
          snapshot_value: "9000.00",
          market_price: "185.00",
          market_value: "9250.00",
          created_at: "2025-06-01T00:00:00Z",
          cost_basis: null,
          gain_loss: null,
          gain_loss_percent: null,
          lot_coverage: null,
          lot_count: null,
          realized_gain_loss: null,
        },
      ];

      vi.mocked(accountsApi.get).mockResolvedValue({ data: mockAccount } as never);
      vi.mocked(accountsApi.getHoldings).mockResolvedValue({ data: mixedHoldings } as never);
      vi.mocked(accountsApi.getActivities).mockResolvedValue({ data: [] } as never);

      renderAccountDetails();

      await waitFor(() => {
        expect(screen.getByText("Test Brokerage")).toBeInTheDocument();
      });

      // Columns should be visible (from VTI with lots)
      expect(screen.getByText("Cost Basis")).toBeInTheDocument();

      // AAPL row should show dashes for cost basis and gain/loss
      const dashes = screen.getAllByText("-");
      expect(dashes.length).toBe(2);
    });
  });
});
