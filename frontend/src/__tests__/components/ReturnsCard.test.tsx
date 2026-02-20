import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ReturnsCard } from "../../components/dashboard/ReturnsCard";

const mockGetReturns = vi.fn();

vi.mock("@/api", () => ({
  portfolioApi: {
    getReturns: (...args: unknown[]) => mockGetReturns(...args),
  },
}));

function renderCard() {
  return render(
    <MemoryRouter>
      <ReturnsCard />
    </MemoryRouter>
  );
}

const makePeriod = (
  period: string,
  irr: string | null,
  hasSufficientData = true
) => ({
  period,
  irr,
  start_date: "2025-01-01",
  end_date: "2025-06-15",
  has_sufficient_data: hasSufficientData,
});

describe("ReturnsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when no portfolio data", async () => {
    mockGetReturns.mockResolvedValue({
      data: { portfolio: null, accounts: [] },
    });

    const { container } = renderCard();

    await waitFor(() => {
      expect(mockGetReturns).toHaveBeenCalled();
    });

    expect(container.firstChild).toBeNull();
  });

  it("renders period labels and IRR values", async () => {
    mockGetReturns.mockResolvedValue({
      data: {
        portfolio: {
          scope_id: "portfolio",
          scope_name: "Portfolio",
          periods: [
            makePeriod("1D", "0.0012"),
            makePeriod("1M", "0.0523"),
            makePeriod("QTD", "0.0834"),
            makePeriod("3M", "0.0712"),
            makePeriod("YTD", "0.1245"),
            makePeriod("1Y", "0.1890"),
          ],
        },
        accounts: [],
      },
    });

    renderCard();

    await waitFor(() => {
      expect(screen.getByText("Returns (IRR)")).toBeInTheDocument();
    });

    // Period labels
    expect(screen.getByText("1D")).toBeInTheDocument();
    expect(screen.getByText("1M")).toBeInTheDocument();
    expect(screen.getByText("QTD")).toBeInTheDocument();
    expect(screen.getByText("YTD")).toBeInTheDocument();
    expect(screen.getByText("1Y")).toBeInTheDocument();

    // IRR values (0.0523 → "5.23%")
    expect(screen.getByText("5.23%")).toBeInTheDocument();
    expect(screen.getByText("12.45%")).toBeInTheDocument();
  });

  it("shows N/A for null IRR", async () => {
    mockGetReturns.mockResolvedValue({
      data: {
        portfolio: {
          scope_id: "portfolio",
          scope_name: "Portfolio",
          periods: [
            makePeriod("1D", null),
            makePeriod("1M", "0.05"),
          ],
        },
        accounts: [],
      },
    });

    renderCard();

    await waitFor(() => {
      expect(screen.getByText("N/A")).toBeInTheDocument();
    });

    expect(screen.getByText("5.00%")).toBeInTheDocument();
  });

  it("applies positive color class for gains", async () => {
    mockGetReturns.mockResolvedValue({
      data: {
        portfolio: {
          scope_id: "portfolio",
          scope_name: "Portfolio",
          periods: [makePeriod("1D", "0.05")],
        },
        accounts: [],
      },
    });

    renderCard();

    await waitFor(() => {
      expect(screen.getByText("5.00%")).toBeInTheDocument();
    });

    const valueEl = screen.getByText("5.00%");
    expect(valueEl.className).toContain("text-tf-positive");
  });

  it("applies negative color class for losses", async () => {
    mockGetReturns.mockResolvedValue({
      data: {
        portfolio: {
          scope_id: "portfolio",
          scope_name: "Portfolio",
          periods: [makePeriod("1M", "-0.03")],
        },
        accounts: [],
      },
    });

    renderCard();

    await waitFor(() => {
      expect(screen.getByText("-3.00%")).toBeInTheDocument();
    });

    const valueEl = screen.getByText("-3.00%");
    expect(valueEl.className).toContain("text-tf-negative");
  });

  it("passes account_ids to API when accountIds prop is set", async () => {
    mockGetReturns.mockResolvedValue({
      data: {
        portfolio: {
          scope_id: "portfolio",
          scope_name: "Portfolio",
          periods: [makePeriod("1D", "0.01")],
        },
        accounts: [],
      },
    });

    render(
      <MemoryRouter>
        <ReturnsCard accountIds="id1,id2" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mockGetReturns).toHaveBeenCalledWith(
        expect.objectContaining({ account_ids: "id1,id2" })
      );
    });
  });

  it("links to returns detail page", async () => {
    mockGetReturns.mockResolvedValue({
      data: {
        portfolio: {
          scope_id: "portfolio",
          scope_name: "Portfolio",
          periods: [makePeriod("1D", "0.01")],
        },
        accounts: [],
      },
    });

    renderCard();

    await waitFor(() => {
      expect(screen.getByText("Returns (IRR)")).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: /view returns detail/i });
    expect(link).toHaveAttribute("href", "/returns");
  });
});
