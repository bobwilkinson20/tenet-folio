/**
 * Tests for useDashboard hook - specifically the staleness refetch behavior
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useDashboard } from "@/hooks/useDashboard";

const mockRefetch = vi.fn();
const mockSetDashboardStale = vi.fn();
let mockDashboardStale = false;
let lastFetchFn: (() => unknown) | null = null;

vi.mock("@/hooks/useFetch", () => ({
  useFetch: (fn: () => unknown) => {
    lastFetchFn = fn;
    return {
      data: { accounts: [], net_worth: 0, allocations: [] },
      loading: false,
      error: null,
      refetch: mockRefetch,
    };
  },
}));

const mockGet = vi.fn().mockResolvedValue({ data: {} });

vi.mock("@/api", () => ({
  dashboardApi: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

vi.mock("@/context", () => ({
  usePortfolioContext: () => ({
    dashboardStale: mockDashboardStale,
    setDashboardStale: mockSetDashboardStale,
  }),
}));

describe("useDashboard - staleness refetch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDashboardStale = false;
    lastFetchFn = null;
  });

  it("should not refetch when dashboardStale is false", async () => {
    mockDashboardStale = false;

    renderHook(() => useDashboard());

    // Wait for initial effects to settle
    await waitFor(() => {
      // refetch is called once on mount
      expect(mockRefetch).toHaveBeenCalledTimes(1);
    });

    // setDashboardStale should not have been called
    expect(mockSetDashboardStale).not.toHaveBeenCalled();
  });

  it("should refetch and clear stale flag when dashboardStale is true", async () => {
    mockDashboardStale = true;

    renderHook(() => useDashboard());

    await waitFor(() => {
      // refetch is called on mount and once for staleness
      expect(mockRefetch).toHaveBeenCalledTimes(2);
    });

    // Should clear the stale flag after refetching
    expect(mockSetDashboardStale).toHaveBeenCalledWith(false);
  });

  it("should pass allocation_only param to API when allocationOnly is true", async () => {
    renderHook(() => useDashboard(true));

    // The fetch function passed to useFetch should call dashboardApi.get with params
    expect(lastFetchFn).not.toBeNull();
    await lastFetchFn!();

    expect(mockGet).toHaveBeenCalledWith({ allocation_only: true });
  });

  it("should not pass params to API when allocationOnly is false", async () => {
    renderHook(() => useDashboard(false));

    expect(lastFetchFn).not.toBeNull();
    await lastFetchFn!();

    expect(mockGet).toHaveBeenCalledWith(undefined);
  });

  it("should pass account_ids when selectedAccountIds is provided", async () => {
    renderHook(() => useDashboard(false, true, ["id1", "id2"]));

    expect(lastFetchFn).not.toBeNull();
    await lastFetchFn!();

    expect(mockGet).toHaveBeenCalledWith({ account_ids: "id1,id2" });
  });

  it("should pass both allocation_only and account_ids when both set", async () => {
    renderHook(() => useDashboard(true, true, ["id1"]));

    expect(lastFetchFn).not.toBeNull();
    await lastFetchFn!();

    expect(mockGet).toHaveBeenCalledWith({
      allocation_only: true,
      account_ids: "id1",
    });
  });

  it("should not pass account_ids when selectedAccountIds is null", async () => {
    renderHook(() => useDashboard(false, true, null));

    expect(lastFetchFn).not.toBeNull();
    await lastFetchFn!();

    expect(mockGet).toHaveBeenCalledWith(undefined);
  });

  it("should not refetch when enabled is false", async () => {
    renderHook(() => useDashboard(false, false));

    await waitFor(() => {
      expect(mockRefetch).not.toHaveBeenCalled();
    });
  });

  it("should refetch when enabled transitions from false to true", async () => {
    let enabled = false;
    const { rerender } = renderHook(() => useDashboard(false, enabled));

    // Should not have fetched while disabled
    expect(mockRefetch).not.toHaveBeenCalled();

    // Enable fetching
    enabled = true;
    rerender();

    await waitFor(() => {
      expect(mockRefetch).toHaveBeenCalledTimes(1);
    });
  });
});
