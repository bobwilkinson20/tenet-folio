import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useTheme } from "@/hooks/useTheme";

let mockPrefs: Record<string, unknown> = {};
const mockSetPreference = vi.fn((key: string, value: unknown) => {
  mockPrefs[key] = value;
});

vi.mock("@/hooks/usePreferences", () => ({
  usePreferences: () => ({
    getPreference: (key: string, defaultValue: unknown) =>
      key in mockPrefs ? mockPrefs[key] : defaultValue,
    setPreference: mockSetPreference,
    loading: false,
  }),
}));

let matchMediaListeners: Array<() => void> = [];

const mockLocalStorage: Record<string, string> = {};
const localStorageMock = {
  getItem: vi.fn((key: string) => mockLocalStorage[key] ?? null),
  setItem: vi.fn((key: string, value: string) => {
    mockLocalStorage[key] = value;
  }),
  removeItem: vi.fn((key: string) => {
    delete mockLocalStorage[key];
  }),
};

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query === "(prefers-color-scheme: light)" ? matches : !matches,
      media: query,
      addEventListener: (_: string, cb: () => void) => {
        matchMediaListeners.push(cb);
      },
      removeEventListener: (_: string, cb: () => void) => {
        matchMediaListeners = matchMediaListeners.filter((l) => l !== cb);
      },
    })),
  });
}

describe("useTheme", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    matchMediaListeners = [];
    mockPrefs = {};
    document.documentElement.removeAttribute("data-theme");

    // Mock localStorage
    Object.keys(mockLocalStorage).forEach((k) => delete mockLocalStorage[k]);
    Object.defineProperty(window, "localStorage", {
      writable: true,
      value: localStorageMock,
    });

    // Add meta theme-color for tests
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "theme-color");
      document.head.appendChild(meta);
    }

    mockMatchMedia(false); // default: system prefers dark
  });

  it("defaults to system theme", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("system");
  });

  it("resolves system mode via matchMedia (dark)", () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useTheme());

    expect(result.current.resolvedTheme).toBe("dark");
  });

  it("resolves system mode via matchMedia (light)", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme());

    expect(result.current.resolvedTheme).toBe("light");
  });

  it("sets data-theme='light' when resolved theme is light", () => {
    mockMatchMedia(true);
    renderHook(() => useTheme());

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("removes data-theme when resolved theme is dark", () => {
    document.documentElement.setAttribute("data-theme", "light");
    mockMatchMedia(false);
    renderHook(() => useTheme());

    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("setTheme persists to preferences and localStorage", () => {
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("light");
    });

    expect(mockSetPreference).toHaveBeenCalledWith("theme.mode", "light");
    expect(localStorageMock.setItem).toHaveBeenCalledWith("tf-theme", "light");
  });

  it("updates meta theme-color", () => {
    mockMatchMedia(true); // light system theme
    renderHook(() => useTheme());

    const meta = document.querySelector('meta[name="theme-color"]');
    expect(meta?.getAttribute("content")).toBe("#f8fafc");
  });

  it("reads stored preference on mount", () => {
    mockPrefs = { "theme.mode": "dark" };
    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("dark");
    expect(result.current.resolvedTheme).toBe("dark");
  });

  it("responds to OS theme changes in system mode", async () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useTheme());

    expect(result.current.resolvedTheme).toBe("dark");

    // Simulate OS switching to light
    mockMatchMedia(true);
    act(() => {
      matchMediaListeners.forEach((cb) => cb());
    });

    await waitFor(() => {
      expect(result.current.resolvedTheme).toBe("light");
    });
  });
});
