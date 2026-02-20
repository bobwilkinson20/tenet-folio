import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AssetTypeDetailsPage } from "../../pages/AssetTypeDetails";

vi.mock("../../api/assetTypes", () => ({
  assetTypeApi: {
    getHoldings: vi.fn(),
  },
}));

import { assetTypeApi } from "../../api/assetTypes";

const mockDetail = {
  asset_type_id: "at-1",
  asset_type_name: "US Stocks",
  asset_type_color: "#3B82F6",
  total_value: "25000.00",
  holdings: [
    {
      holding_id: "h-1",
      account_id: "acc-1",
      account_name: "Vanguard Brokerage",
      ticker: "VTI",
      security_name: "Vanguard Total Stock Market ETF",
      market_value: "15000.00",
    },
    {
      holding_id: "h-2",
      account_id: "acc-2",
      account_name: "Fidelity 401k",
      ticker: "AAPL",
      security_name: "Apple Inc.",
      market_value: "10000.00",
    },
  ],
};

function renderPage(id = "at-1") {
  return render(
    <MemoryRouter initialEntries={[`/asset-types/${id}`]}>
      <Routes>
        <Route path="/asset-types/:id" element={<AssetTypeDetailsPage />} />
        <Route path="/accounts/:id" element={<div>Account Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AssetTypeDetailsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading state initially", () => {
    vi.mocked(assetTypeApi.getHoldings).mockReturnValue(new Promise(() => {}) as never);

    renderPage();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders asset type details with holdings", async () => {
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: mockDetail } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("US Stocks")).toBeInTheDocument();
    });

    expect(screen.getByText("$25,000.00")).toBeInTheDocument();
    expect(screen.getByText("VTI")).toBeInTheDocument();
    expect(screen.getByText("Vanguard Total Stock Market ETF")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
    expect(screen.getByText("Vanguard Brokerage")).toBeInTheDocument();
    expect(screen.getByText("Fidelity 401k")).toBeInTheDocument();
  });

  it("renders error state", async () => {
    vi.mocked(assetTypeApi.getHoldings).mockRejectedValue(new Error("Network error"));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Failed to load asset type details.")).toBeInTheDocument();
    });
  });

  it("renders empty state when no holdings", async () => {
    const emptyDetail = {
      ...mockDetail,
      total_value: "0.00",
      holdings: [],
    };
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: emptyDetail } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No holdings found.")).toBeInTheDocument();
    });
  });

  it("account names are links to account pages", async () => {
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: mockDetail } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Vanguard Brokerage")).toBeInTheDocument();
    });

    const link = screen.getByText("Vanguard Brokerage");
    expect(link.closest("a")).toHaveAttribute("href", "/accounts/acc-1");

    const link2 = screen.getByText("Fidelity 401k");
    expect(link2.closest("a")).toHaveAttribute("href", "/accounts/acc-2");
  });

  it("renders Unknown title for unassigned route", async () => {
    const unassignedDetail = {
      asset_type_id: "unassigned",
      asset_type_name: "Unknown",
      asset_type_color: "#9CA3AF",
      total_value: "5000.00",
      holdings: [
        {
          holding_id: "h-3",
          account_id: "acc-1",
          account_name: "My Account",
          ticker: "XYZ",
          security_name: null,
          market_value: "5000.00",
        },
      ],
    };
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: unassignedDetail } as never);

    renderPage("unassigned");

    await waitFor(() => {
      expect(screen.getByText("Unknown")).toBeInTheDocument();
    });

    expect(screen.getByText("XYZ")).toBeInTheDocument();
  });

  it("sorts groups by total value descending", async () => {
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: mockDetail } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("VTI")).toBeInTheDocument();
    });

    const rows = screen.getAllByRole("row");
    // Row 0: header
    // Row 1: VTI flat row ($15,000) - single holding
    // Row 2: AAPL flat row ($10,000) - single holding
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent("VTI");
    expect(rows[2]).toHaveTextContent("AAPL");
  });

  it("renders single-holding groups as flat rows with all fields", async () => {
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: mockDetail } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("VTI")).toBeInTheDocument();
    });

    const rows = screen.getAllByRole("row");
    // Single-holding groups render as one flat row each
    expect(rows).toHaveLength(3); // header + 2 flat rows

    // VTI row has all four fields in one row
    expect(rows[1]).toHaveTextContent("Vanguard Brokerage");
    expect(rows[1]).toHaveTextContent("VTI");
    expect(rows[1]).toHaveTextContent("Vanguard Total Stock Market ETF");
    expect(rows[1]).toHaveTextContent("$15,000.00");

    // AAPL row has all four fields in one row
    expect(rows[2]).toHaveTextContent("Fidelity 401k");
    expect(rows[2]).toHaveTextContent("AAPL");
    expect(rows[2]).toHaveTextContent("Apple Inc.");
    expect(rows[2]).toHaveTextContent("$10,000.00");

    // No group header styling on flat rows
    expect(rows[1].className).not.toContain("bg-tf-bg-secondary");
  });

  it("shows em-dash for _MAN: synthetic tickers", async () => {
    const detailWithSynthetic = {
      ...mockDetail,
      holdings: [
        {
          holding_id: "h-3",
          account_id: "acc-3",
          account_name: "Manual Account",
          ticker: "_MAN:abc123456789",
          security_name: "Primary Residence",
          market_value: "500000.00",
        },
      ],
    };
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: detailWithSynthetic } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("US Stocks")).toBeInTheDocument();
    });

    // Security name should be displayed in group header
    expect(screen.getByText("Primary Residence")).toBeInTheDocument();

    // Synthetic ticker should NOT be displayed
    expect(screen.queryByText("_MAN:abc123456789")).not.toBeInTheDocument();

    // Em-dash should be shown in ticker column (first column)
    const rows = screen.getAllByRole("row");
    const groupHeaderCells = rows[1].querySelectorAll("td");
    expect(groupHeaderCells[0].textContent).toBe("—");
  });

  it("shows em-dash for _SF: synthetic tickers", async () => {
    const detailWithSynthetic = {
      ...mockDetail,
      holdings: [
        {
          holding_id: "h-4",
          account_id: "acc-4",
          account_name: "529 Plan",
          ticker: "_SF:xyz98765",
          security_name: "Vanguard Target Trust",
          market_value: "50000.00",
        },
      ],
    };
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: detailWithSynthetic } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("US Stocks")).toBeInTheDocument();
    });

    // Security name should be displayed in group header
    expect(screen.getByText("Vanguard Target Trust")).toBeInTheDocument();

    // Synthetic ticker should NOT be displayed
    expect(screen.queryByText("_SF:xyz98765")).not.toBeInTheDocument();

    // Em-dash should be shown in ticker column (first column)
    const rows = screen.getAllByRole("row");
    const groupHeaderCells = rows[1].querySelectorAll("td");
    expect(groupHeaderCells[0].textContent).toBe("—");
  });

  it("shows actual tickers for regular securities", async () => {
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: mockDetail } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("US Stocks")).toBeInTheDocument();
    });

    // Regular tickers should be displayed
    expect(screen.getByText("VTI")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("groups holdings with the same ticker together", async () => {
    const multiAccountDetail = {
      ...mockDetail,
      total_value: "35000.00",
      holdings: [
        {
          holding_id: "h-1",
          account_id: "acc-1",
          account_name: "Vanguard Brokerage",
          ticker: "VTI",
          security_name: "Vanguard Total Stock Market ETF",
          market_value: "15000.00",
        },
        {
          holding_id: "h-2",
          account_id: "acc-2",
          account_name: "Fidelity 401k",
          ticker: "AAPL",
          security_name: "Apple Inc.",
          market_value: "10000.00",
        },
        {
          holding_id: "h-3",
          account_id: "acc-3",
          account_name: "Schwab IRA",
          ticker: "VTI",
          security_name: "Vanguard Total Stock Market ETF",
          market_value: "10000.00",
        },
      ],
    };
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: multiAccountDetail } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("VTI")).toBeInTheDocument();
    });

    const rows = screen.getAllByRole("row");
    // Row 0: header
    // Row 1: VTI group header (total $25,000) - multi-holding
    // Row 2: VTI - Vanguard Brokerage ($15,000)
    // Row 3: VTI - Schwab IRA ($10,000)
    // Row 4: AAPL flat row ($10,000) - single holding
    expect(rows).toHaveLength(5);

    // VTI group header shows ticker, name, "All accounts", and total value
    expect(rows[1]).toHaveTextContent("VTI");
    expect(rows[1]).toHaveTextContent("Vanguard Total Stock Market ETF");
    expect(rows[1]).toHaveTextContent("All accounts");
    expect(rows[1]).toHaveTextContent("$25,000.00");

    // VTI holdings appear right after the group header
    expect(rows[2]).toHaveTextContent("Vanguard Brokerage");
    expect(rows[2]).toHaveTextContent("$15,000.00");
    expect(rows[3]).toHaveTextContent("Schwab IRA");
    expect(rows[3]).toHaveTextContent("$10,000.00");

    // AAPL renders as a flat row with all fields
    expect(rows[4]).toHaveTextContent("Fidelity 401k");
    expect(rows[4]).toHaveTextContent("AAPL");
    expect(rows[4]).toHaveTextContent("Apple Inc.");
    expect(rows[4]).toHaveTextContent("$10,000.00");
  });

  it("orders groups by total value and holdings within groups by individual value", async () => {
    const multiHoldingDetail = {
      ...mockDetail,
      total_value: "40000.00",
      holdings: [
        {
          holding_id: "h-1",
          account_id: "acc-1",
          account_name: "Small Account",
          ticker: "VTI",
          security_name: "Vanguard Total Stock Market ETF",
          market_value: "5000.00",
        },
        {
          holding_id: "h-2",
          account_id: "acc-2",
          account_name: "Big Account",
          ticker: "VTI",
          security_name: "Vanguard Total Stock Market ETF",
          market_value: "20000.00",
        },
        {
          holding_id: "h-3",
          account_id: "acc-3",
          account_name: "Mid Account",
          ticker: "AAPL",
          security_name: "Apple Inc.",
          market_value: "15000.00",
        },
      ],
    };
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: multiHoldingDetail } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("VTI")).toBeInTheDocument();
    });

    const rows = screen.getAllByRole("row");
    // Row 0: header
    // Row 1: VTI group header ($25,000 total) - multi-holding
    // Row 2: VTI - Big Account ($20,000)
    // Row 3: VTI - Small Account ($5,000)
    // Row 4: AAPL flat row ($15,000) - single holding
    expect(rows).toHaveLength(5);

    // VTI group ($25,000 total) should come before AAPL ($15,000)
    expect(rows[1]).toHaveTextContent("VTI");
    expect(rows[1]).toHaveTextContent("$25,000.00");

    // Within VTI group, Big Account ($20,000) before Small Account ($5,000)
    expect(rows[2]).toHaveTextContent("Big Account");
    expect(rows[3]).toHaveTextContent("Small Account");

    // AAPL renders as flat row
    expect(rows[4]).toHaveTextContent("AAPL");
    expect(rows[4]).toHaveTextContent("Mid Account");
  });

  it("group header shows bold styling for multi-holding groups", async () => {
    const multiHoldingDetail = {
      ...mockDetail,
      holdings: [
        {
          holding_id: "h-1",
          account_id: "acc-1",
          account_name: "Account A",
          ticker: "VTI",
          security_name: "Vanguard Total Stock Market ETF",
          market_value: "15000.00",
        },
        {
          holding_id: "h-2",
          account_id: "acc-2",
          account_name: "Account B",
          ticker: "VTI",
          security_name: "Vanguard Total Stock Market ETF",
          market_value: "10000.00",
        },
      ],
    };
    vi.mocked(assetTypeApi.getHoldings).mockResolvedValue({ data: multiHoldingDetail } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("VTI")).toBeInTheDocument();
    });

    const rows = screen.getAllByRole("row");
    // Group header row should have the secondary background class
    expect(rows[1].className).toContain("bg-tf-bg-secondary");

    // Ticker cell in group header should be bold (first column)
    const tickerCell = rows[1].querySelectorAll("td")[0];
    expect(tickerCell.className).toContain("font-bold");
  });
});
