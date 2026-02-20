/**
 * Tests for usePreferences hook
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { usePreferences } from "@/hooks/usePreferences";

const mockGetAll = vi.fn();
const mockSet = vi.fn();

vi.mock("@/api/preferences", () => ({
  preferencesApi: {
    getAll: (...args: unknown[]) => mockGetAll(...args),
    set: (...args: unknown[]) => mockSet(...args),
  },
}));

describe("usePreferences", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetAll.mockResolvedValue({ data: {} });
    mockSet.mockResolvedValue({ data: {} });
  });

  it("starts in loading state", () => {
    const { result } = renderHook(() => usePreferences());
    expect(result.current.loading).toBe(true);
  });

  it("loads preferences on mount", async () => {
    mockGetAll.mockResolvedValue({
      data: { "accounts.hideInactive": true, theme: "dark" },
    });

    const { result } = renderHook(() => usePreferences());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.getPreference("accounts.hideInactive", false)).toBe(
      true,
    );
    expect(result.current.getPreference("theme", "light")).toBe("dark");
  });

  it("returns default value for missing key", async () => {
    mockGetAll.mockResolvedValue({ data: {} });

    const { result } = renderHook(() => usePreferences());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.getPreference("missing", "default")).toBe("default");
    expect(result.current.getPreference("missing_bool", false)).toBe(false);
  });

  it("returns default value while still loading", () => {
    // Never resolves during this test
    mockGetAll.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => usePreferences());

    expect(result.current.getPreference("any.key", "fallback")).toBe(
      "fallback",
    );
  });

  it("optimistically updates preference", async () => {
    mockGetAll.mockResolvedValue({ data: {} });

    const { result } = renderHook(() => usePreferences());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    act(() => {
      result.current.setPreference("accounts.hideInactive", true);
    });

    expect(result.current.getPreference("accounts.hideInactive", false)).toBe(
      true,
    );
    expect(mockSet).toHaveBeenCalledWith("accounts.hideInactive", true);
  });

  it("reverts on API error", async () => {
    mockGetAll.mockResolvedValue({ data: { "my.key": "original" } });
    mockSet.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => usePreferences());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    act(() => {
      result.current.setPreference("my.key", "new_value");
    });

    // Optimistic update applied immediately
    expect(result.current.getPreference("my.key", "")).toBe("new_value");

    // After rejection, reverts
    await waitFor(() => {
      expect(result.current.getPreference("my.key", "")).toBe("original");
    });
  });

  it("handles failed initial load gracefully", async () => {
    mockGetAll.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => usePreferences());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Should still work with defaults
    expect(result.current.getPreference("any", "default")).toBe("default");
  });
});
