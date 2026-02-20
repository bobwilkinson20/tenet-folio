/**
 * Tests for useAccountDetails hook
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useAccountDetails } from "@/hooks/useAccountDetails";
import type { Account, Activity } from "@/types";
import type { Holding } from "@/types/sync_session";

const mockAccount: Account = {
  id: "acc-1",
  name: "Test Account",
  provider_name: "Manual",
  external_id: "ext-1",
  institution_name: "Test Bank",
  is_active: true,
  include_in_allocation: true,
  assigned_asset_class_id: null,
  created_at: "2024-01-01",
  updated_at: "2024-01-01",
};

const mockHoldings: Holding[] = [
  {
    id: "h-1",
    account_snapshot_id: "snap-1",
    ticker: "AAPL",
    quantity: 10,
    snapshot_price: 150,
    snapshot_value: 1500,
    created_at: "2024-01-01",
  },
];

const mockActivities: Activity[] = [
  {
    id: "act-1",
    account_id: "acc-1",
    provider_name: "Manual",
    external_id: "ext-act-1",
    type: "buy",
    description: null,
    ticker: "AAPL",
    units: "10",
    price: "150",
    amount: "1500",
    currency: "USD",
    fee: null,
    settlement_date: null,
    activity_date: "2024-01-01",
    is_reviewed: false,
    notes: null,
    user_modified: false,
    created_at: "2024-01-01",
  },
];

const mockGet = vi.fn();
const mockGetHoldings = vi.fn();
const mockGetActivities = vi.fn();

vi.mock("@/api", () => ({
  accountsApi: {
    get: (...args: unknown[]) => mockGet(...args),
    getHoldings: (...args: unknown[]) => mockGetHoldings(...args),
    getActivities: (...args: unknown[]) => mockGetActivities(...args),
  },
}));

describe("useAccountDetails", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockResolvedValue({ data: mockAccount });
    mockGetHoldings.mockResolvedValue({ data: mockHoldings });
    mockGetActivities.mockResolvedValue({ data: mockActivities });
  });

  it("should fetch account, holdings, and activities on mount", async () => {
    const { result } = renderHook(() => useAccountDetails("acc-1"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockGet).toHaveBeenCalledWith("acc-1");
    expect(mockGetHoldings).toHaveBeenCalledWith("acc-1");
    expect(mockGetActivities).toHaveBeenCalledWith("acc-1");
    expect(result.current.account).toEqual(mockAccount);
    expect(result.current.holdings).toEqual(mockHoldings);
    expect(result.current.activities).toEqual(mockActivities);
  });

  it("should not fetch when id is undefined", async () => {
    const { result } = renderHook(() => useAccountDetails(undefined));

    // Give it a tick to settle
    await new Promise((r) => setTimeout(r, 50));

    expect(mockGet).not.toHaveBeenCalled();
    expect(result.current.account).toBeNull();
    expect(result.current.holdings).toEqual([]);
    expect(result.current.activities).toEqual([]);
  });

  it("should return error when fetch fails", async () => {
    mockGet.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useAccountDetails("acc-1"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.account).toBeNull();
  });

  it("should refetch holdings without refetching account or activities", async () => {
    const { result } = renderHook(() => useAccountDetails("acc-1"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    vi.clearAllMocks();

    const updatedHoldings: Holding[] = [
      ...mockHoldings,
      {
        id: "h-2",
        account_snapshot_id: "snap-1",
        ticker: "MSFT",
        quantity: 5,
        snapshot_price: 300,
        snapshot_value: 1500,
        created_at: "2024-01-01",
      },
    ];
    mockGetHoldings.mockResolvedValue({ data: updatedHoldings });

    await result.current.refetchHoldings();

    expect(mockGetHoldings).toHaveBeenCalledWith("acc-1");
    expect(mockGet).not.toHaveBeenCalled();
    expect(mockGetActivities).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(result.current.holdings).toEqual(updatedHoldings);
    });
    // Account and activities should remain unchanged
    expect(result.current.account).toEqual(mockAccount);
    expect(result.current.activities).toEqual(mockActivities);
  });

  it("should refetch when id changes", async () => {
    const { result, rerender } = renderHook(
      ({ id }) => useAccountDetails(id),
      { initialProps: { id: "acc-1" } }
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    vi.clearAllMocks();

    const otherAccount = { ...mockAccount, id: "acc-2", name: "Other" };
    mockGet.mockResolvedValue({ data: otherAccount });

    rerender({ id: "acc-2" });

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("acc-2");
    });
  });
});
