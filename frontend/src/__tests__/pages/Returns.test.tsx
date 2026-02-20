import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ReturnsPage } from "../../pages/Returns";

const mockGetReturns = vi.fn();

vi.mock("@/api", () => ({
  portfolioApi: {
    getReturns: (...args: unknown[]) => mockGetReturns(...args),
  },
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <ReturnsPage />
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

describe("ReturnsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders portfolio and account returns", async () => {
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
        accounts: [
          {
            scope_id: "acc-1",
            scope_name: "Brokerage Account",
            periods: [
              makePeriod("1D", "0.0015"),
              makePeriod("1M", "0.06"),
              makePeriod("QTD", "0.09"),
              makePeriod("3M", "0.08"),
              makePeriod("YTD", "0.15"),
              makePeriod("1Y", "0.22"),
            ],
          },
          {
            scope_id: "acc-2",
            scope_name: "Retirement Account",
            periods: [
              makePeriod("1D", "-0.002"),
              makePeriod("1M", "0.04"),
              makePeriod("QTD", "0.07"),
              makePeriod("3M", "0.06"),
              makePeriod("YTD", "0.10"),
              makePeriod("1Y", "0.16"),
            ],
          },
        ],
      },
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Returns")).toBeInTheDocument();
    });

    // Portfolio section
    expect(screen.getByText("Portfolio Returns (IRR)")).toBeInTheDocument();
    expect(screen.getByText("12.45%")).toBeInTheDocument();

    // Account section
    expect(screen.getByText("Account Returns (IRR)")).toBeInTheDocument();
    expect(screen.getByText("Brokerage Account")).toBeInTheDocument();
    expect(screen.getByText("Retirement Account")).toBeInTheDocument();
  });

  it("shows N/A for missing data", async () => {
    mockGetReturns.mockResolvedValue({
      data: {
        portfolio: {
          scope_id: "portfolio",
          scope_name: "Portfolio",
          periods: [
            makePeriod("1D", null),
            makePeriod("1M", null),
            makePeriod("QTD", null),
            makePeriod("3M", null),
            makePeriod("YTD", null),
            makePeriod("1Y", null),
          ],
        },
        accounts: [],
      },
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Portfolio Returns (IRR)")).toBeInTheDocument();
    });

    const naElements = screen.getAllByText("N/A");
    expect(naElements.length).toBe(6);
  });

  it("shows empty state when no data", async () => {
    mockGetReturns.mockResolvedValue({
      data: { portfolio: null, accounts: [] },
    });

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(/no returns data available/i)
      ).toBeInTheDocument();
    });
  });

  it("navigates back on back button click", async () => {
    mockGetReturns.mockResolvedValue({
      data: { portfolio: null, accounts: [] },
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Returns")).toBeInTheDocument();
    });

    const backButton = screen.getByLabelText("Go back");
    backButton.click();
    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });
});
