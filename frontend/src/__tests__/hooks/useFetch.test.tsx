/**
 * Tests for useFetch hook - specifically the stale request protection
 */

import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useFetch } from "@/hooks/useFetch";

describe("useFetch", () => {
  it("should fetch data successfully", async () => {
    const mockData = { items: [1, 2, 3] };
    const fetchFn = vi.fn().mockResolvedValue({ data: mockData });

    const { result } = renderHook(() => useFetch(fetchFn));

    await act(async () => {
      await result.current.refetch();
    });

    expect(result.current.data).toEqual(mockData);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("should ignore stale responses when a newer request is in flight", async () => {
    let resolveFirst: (value: { data: string }) => void;
    let resolveSecond: (value: { data: string }) => void;

    const firstPromise = new Promise<{ data: string }>((r) => {
      resolveFirst = r;
    });
    const secondPromise = new Promise<{ data: string }>((r) => {
      resolveSecond = r;
    });

    let callCount = 0;
    const fetchFn = vi.fn().mockImplementation(() => {
      callCount++;
      return callCount === 1 ? firstPromise : secondPromise;
    });

    const { result } = renderHook(() => useFetch(fetchFn));

    // Start first request
    let firstRefetch: Promise<void>;
    act(() => {
      firstRefetch = result.current.refetch();
    });

    // Start second request before first resolves
    let secondRefetch: Promise<void>;
    act(() => {
      secondRefetch = result.current.refetch();
    });

    // Resolve second request first (out of order)
    await act(async () => {
      resolveSecond!({ data: "second-correct" });
      await secondRefetch!;
    });

    expect(result.current.data).toBe("second-correct");

    // Now resolve first (stale) request - should be ignored
    await act(async () => {
      resolveFirst!({ data: "first-stale" });
      await firstRefetch!;
    });

    // Data should still be from the second request
    expect(result.current.data).toBe("second-correct");
  });

  it("should ignore stale error responses", async () => {
    let resolveSecond: (value: { data: string }) => void;
    let rejectFirst: (reason: Error) => void;

    const firstPromise = new Promise<{ data: string }>((_, reject) => {
      rejectFirst = reject;
    });
    const secondPromise = new Promise<{ data: string }>((resolve) => {
      resolveSecond = resolve;
    });

    let callCount = 0;
    const fetchFn = vi.fn().mockImplementation(() => {
      callCount++;
      return callCount === 1 ? firstPromise : secondPromise;
    });

    const { result } = renderHook(() => useFetch(fetchFn));

    // Start first request
    let firstRefetch: Promise<void>;
    act(() => {
      firstRefetch = result.current.refetch();
    });

    // Start second request
    let secondRefetch: Promise<void>;
    act(() => {
      secondRefetch = result.current.refetch();
    });

    // Resolve second request successfully
    await act(async () => {
      resolveSecond!({ data: "success" });
      await secondRefetch!;
    });

    expect(result.current.data).toBe("success");
    expect(result.current.error).toBeNull();

    // First request fails (stale) - should be ignored
    await act(async () => {
      rejectFirst!(new Error("stale error"));
      await firstRefetch!;
    });

    // Should still show successful data, not the stale error
    expect(result.current.data).toBe("success");
    expect(result.current.error).toBeNull();
  });

  it("should update data via setData", async () => {
    const fetchFn = vi.fn().mockResolvedValue({ data: "initial" });

    const { result } = renderHook(() => useFetch(fetchFn));

    await act(async () => {
      await result.current.refetch();
    });

    expect(result.current.data).toBe("initial");

    act(() => {
      result.current.setData("updated");
    });

    await waitFor(() => {
      expect(result.current.data).toBe("updated");
    });
  });
});
