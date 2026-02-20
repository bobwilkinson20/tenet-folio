/**
 * Tests for NetWorthChart component
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { NetWorthChart } from "@/components/dashboard/NetWorthChart";

// Mock recharts to avoid SVG rendering issues in tests
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 800, height: 300 }}>
        {children}
      </div>
    ),
  };
});

const mockGetValueHistory = vi.fn();

vi.mock("@/api", () => ({
  portfolioApi: {
    getValueHistory: (...args: unknown[]) => mockGetValueHistory(...args),
  },
}));

describe("NetWorthChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should show loading state initially", () => {
    mockGetValueHistory.mockReturnValue(new Promise(() => {})); // never resolves
    render(<NetWorthChart />);
    expect(screen.getByText("Loading chart...")).toBeInTheDocument();
  });

  it("should render chart with data", async () => {
    mockGetValueHistory.mockResolvedValue({
      data: {
        start_date: "2025-01-06",
        end_date: "2025-01-08",
        data_points: [
          { date: "2025-01-06", value: "15500.00" },
          { date: "2025-01-07", value: "15620.00" },
          { date: "2025-01-08", value: "15800.00" },
        ],
      },
    });

    render(<NetWorthChart />);

    await waitFor(() => {
      expect(screen.queryByText("Loading chart...")).not.toBeInTheDocument();
    });

    expect(screen.getByText("Portfolio Value")).toBeInTheDocument();
    expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
  });

  it("should render nothing when no data available", async () => {
    mockGetValueHistory.mockResolvedValue({
      data: {
        start_date: "2025-01-06",
        end_date: "2025-01-08",
        data_points: [],
      },
    });

    const { container } = render(<NetWorthChart />);

    await waitFor(() => {
      expect(screen.queryByText("Loading chart...")).not.toBeInTheDocument();
    });

    expect(container.firstChild).toBeNull();
  });

  it("should show error state on API failure", async () => {
    mockGetValueHistory.mockRejectedValue(new Error("API error"));

    render(<NetWorthChart />);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to load portfolio history")
      ).toBeInTheDocument();
    });
  });

  it("should render time range buttons", async () => {
    mockGetValueHistory.mockResolvedValue({
      data: {
        start_date: "2025-01-06",
        end_date: "2025-01-08",
        data_points: [{ date: "2025-01-06", value: "15500.00" }],
      },
    });

    render(<NetWorthChart />);

    await waitFor(() => {
      expect(screen.queryByText("Loading chart...")).not.toBeInTheDocument();
    });

    for (const label of ["1M", "3M", "6M", "YTD", "1Y", "ALL"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("should default to 3M range", async () => {
    mockGetValueHistory.mockResolvedValue({
      data: {
        start_date: "2025-01-06",
        end_date: "2025-01-08",
        data_points: [{ date: "2025-01-06", value: "15500.00" }],
      },
    });

    render(<NetWorthChart />);

    await waitFor(() => {
      expect(screen.queryByText("Loading chart...")).not.toBeInTheDocument();
    });

    // 3M button should have the active style (bg-tf-accent-primary)
    const button3M = screen.getByText("3M");
    expect(button3M.className).toContain("bg-tf-accent-primary");
  });

  it("should refetch data when range changes", async () => {
    mockGetValueHistory.mockResolvedValue({
      data: {
        start_date: "2025-01-06",
        end_date: "2025-01-08",
        data_points: [{ date: "2025-01-06", value: "15500.00" }],
      },
    });

    render(<NetWorthChart />);

    await waitFor(() => {
      expect(screen.queryByText("Loading chart...")).not.toBeInTheDocument();
    });

    // Initial fetch with 3M default
    expect(mockGetValueHistory).toHaveBeenCalledTimes(1);

    // Click 1Y
    fireEvent.click(screen.getByText("1Y"));

    await waitFor(() => {
      expect(mockGetValueHistory).toHaveBeenCalledTimes(2);
    });
  });

  it("should pass ALL range without start date", async () => {
    mockGetValueHistory.mockResolvedValue({
      data: {
        start_date: "2024-01-01",
        end_date: "2025-01-08",
        data_points: [{ date: "2024-01-01", value: "10000.00" }],
      },
    });

    render(<NetWorthChart />);

    await waitFor(() => {
      expect(screen.queryByText("Loading chart...")).not.toBeInTheDocument();
    });

    // Click ALL
    fireEvent.click(screen.getByText("ALL"));

    await waitFor(() => {
      expect(mockGetValueHistory).toHaveBeenLastCalledWith({
        start: undefined,
        group_by: "total",
        allocation_only: undefined,
        account_ids: undefined,
      });
    });
  });

  it("should pass allocation_only when prop is set", async () => {
    mockGetValueHistory.mockResolvedValue({
      data: {
        start_date: "2025-01-06",
        end_date: "2025-01-08",
        data_points: [{ date: "2025-01-06", value: "15500.00" }],
      },
    });

    render(<NetWorthChart allocationOnly={true} />);

    await waitFor(() => {
      expect(screen.queryByText("Loading chart...")).not.toBeInTheDocument();
    });

    expect(mockGetValueHistory).toHaveBeenCalledWith(
      expect.objectContaining({ allocation_only: true })
    );
  });

  it("should pass account_ids when prop is set", async () => {
    mockGetValueHistory.mockResolvedValue({
      data: {
        start_date: "2025-01-06",
        end_date: "2025-01-08",
        data_points: [{ date: "2025-01-06", value: "15500.00" }],
      },
    });

    render(<NetWorthChart accountIds="id1,id2" />);

    await waitFor(() => {
      expect(screen.queryByText("Loading chart...")).not.toBeInTheDocument();
    });

    expect(mockGetValueHistory).toHaveBeenCalledWith(
      expect.objectContaining({ account_ids: "id1,id2" })
    );
  });

  it("should not pass allocation_only when prop is false", async () => {
    mockGetValueHistory.mockResolvedValue({
      data: {
        start_date: "2025-01-06",
        end_date: "2025-01-08",
        data_points: [{ date: "2025-01-06", value: "15500.00" }],
      },
    });

    render(<NetWorthChart allocationOnly={false} />);

    await waitFor(() => {
      expect(screen.queryByText("Loading chart...")).not.toBeInTheDocument();
    });

    expect(mockGetValueHistory).toHaveBeenCalledWith(
      expect.objectContaining({ allocation_only: undefined })
    );
  });
});
