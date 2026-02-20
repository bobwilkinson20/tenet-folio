import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { CostBasisCard } from "../../components/dashboard/CostBasisCard";

const mockGetCostBasis = vi.fn();

vi.mock("@/api", () => ({
  portfolioApi: {
    getCostBasis: (...args: unknown[]) => mockGetCostBasis(...args),
  },
}));

function renderCard() {
  return render(
    <MemoryRouter>
      <CostBasisCard />
    </MemoryRouter>
  );
}

describe("CostBasisCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when has_lots is false", async () => {
    mockGetCostBasis.mockResolvedValue({
      data: {
        has_lots: false,
        lot_count: 0,
        coverage_percent: null,
        total_cost_basis: null,
        total_market_value: null,
        total_unrealized_gain_loss: null,
        total_realized_gain_loss_ytd: null,
      },
    });

    const { container } = renderCard();

    await waitFor(() => {
      expect(mockGetCostBasis).toHaveBeenCalled();
    });

    expect(container.firstChild).toBeNull();
  });

  it("renders card with unrealized and realized G/L when lots exist", async () => {
    mockGetCostBasis.mockResolvedValue({
      data: {
        has_lots: true,
        lot_count: 5,
        coverage_percent: 85.3,
        total_cost_basis: "50000.00",
        total_market_value: "62000.00",
        total_unrealized_gain_loss: "12000.00",
        total_realized_gain_loss_ytd: "3500.00",
      },
    });

    renderCard();

    await waitFor(() => {
      expect(screen.getByText("Cost Basis")).toBeInTheDocument();
    });

    expect(screen.getByText("$12,000.00")).toBeInTheDocument();
    expect(screen.getByText("$3,500.00")).toBeInTheDocument();
    expect(screen.getByText("Unrealized G/L")).toBeInTheDocument();
    expect(screen.getByText("Realized G/L (YTD)")).toBeInTheDocument();
  });

  it("shows coverage percent and lot count", async () => {
    mockGetCostBasis.mockResolvedValue({
      data: {
        has_lots: true,
        lot_count: 12,
        coverage_percent: 92.5,
        total_cost_basis: "100000.00",
        total_market_value: "115000.00",
        total_unrealized_gain_loss: "15000.00",
        total_realized_gain_loss_ytd: "0.00",
      },
    });

    renderCard();

    await waitFor(() => {
      expect(screen.getByText("12 lots")).toBeInTheDocument();
    });

    expect(screen.getByText("93% coverage")).toBeInTheDocument();
  });

  it("links to realized gains page", async () => {
    mockGetCostBasis.mockResolvedValue({
      data: {
        has_lots: true,
        lot_count: 3,
        coverage_percent: 75.0,
        total_cost_basis: "30000.00",
        total_market_value: "28000.00",
        total_unrealized_gain_loss: "-2000.00",
        total_realized_gain_loss_ytd: "500.00",
      },
    });

    renderCard();

    await waitFor(() => {
      expect(screen.getByText("Cost Basis")).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: /view realized gains/i });
    expect(link).toHaveAttribute("href", "/realized-gains");
  });

  it("passes account_ids to API when accountIds prop is set", async () => {
    mockGetCostBasis.mockResolvedValue({
      data: {
        has_lots: true,
        lot_count: 1,
        coverage_percent: 100,
        total_cost_basis: "1000.00",
        total_market_value: "1200.00",
        total_unrealized_gain_loss: "200.00",
        total_realized_gain_loss_ytd: "0.00",
      },
    });

    render(
      <MemoryRouter>
        <CostBasisCard accountIds="id1,id2" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mockGetCostBasis).toHaveBeenCalledWith({ account_ids: "id1,id2" });
    });
  });

  it("does not pass account_ids when accountIds prop is undefined", async () => {
    mockGetCostBasis.mockResolvedValue({
      data: {
        has_lots: false,
        lot_count: 0,
        coverage_percent: null,
        total_cost_basis: null,
        total_market_value: null,
        total_unrealized_gain_loss: null,
        total_realized_gain_loss_ytd: null,
      },
    });

    render(
      <MemoryRouter>
        <CostBasisCard />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mockGetCostBasis).toHaveBeenCalledWith(undefined);
    });
  });

  it("applies negative color class for losses", async () => {
    mockGetCostBasis.mockResolvedValue({
      data: {
        has_lots: true,
        lot_count: 2,
        coverage_percent: 50.0,
        total_cost_basis: "20000.00",
        total_market_value: "18000.00",
        total_unrealized_gain_loss: "-2000.00",
        total_realized_gain_loss_ytd: "-500.00",
      },
    });

    renderCard();

    await waitFor(() => {
      expect(screen.getByText("Cost Basis")).toBeInTheDocument();
    });

    // Both values should have negative styling
    const unrealizedEl = screen.getByText("-$2,000.00");
    const realizedEl = screen.getByText("-$500.00");
    expect(unrealizedEl.className).toContain("text-tf-negative");
    expect(realizedEl.className).toContain("text-tf-negative");
  });
});
