import { useState, useEffect, useCallback } from "react";
import { usePreferences } from "./usePreferences";

export type ThemeMode = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "tf-theme";
const PREF_KEY = "theme.mode";

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function applyTheme(resolved: ResolvedTheme) {
  if (resolved === "light") {
    document.documentElement.setAttribute("data-theme", "light");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }

  const metaThemeColor = document.querySelector('meta[name="theme-color"]');
  if (metaThemeColor) {
    metaThemeColor.setAttribute(
      "content",
      resolved === "light" ? "#f8fafc" : "#0f172a",
    );
  }
}

export function useTheme() {
  const { getPreference, setPreference, loading } = usePreferences();

  // Theme mode comes directly from preferences — no local state needed
  const theme = getPreference<ThemeMode>(PREF_KEY, "system");

  // Track the OS preference so we can react to media query changes
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(getSystemTheme);

  // Derive resolved theme from mode + OS preference
  const resolvedTheme: ResolvedTheme =
    theme === "system" ? systemTheme : theme;

  // Apply DOM side effects when resolved theme changes
  useEffect(() => {
    applyTheme(resolvedTheme);
  }, [resolvedTheme]);

  // Listen for OS theme changes (subscription — setState in callback is fine)
  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: light)");
    const handler = () => setSystemTheme(getSystemTheme());

    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  const setTheme = useCallback(
    (mode: ThemeMode) => {
      // Persist to API via preferences
      setPreference(PREF_KEY, mode);

      // Write to localStorage for FOUC prevention script
      try {
        localStorage.setItem(STORAGE_KEY, mode);
      } catch {
        // localStorage may be unavailable
      }
    },
    [setPreference],
  );

  return { theme, resolvedTheme, setTheme, loading };
}
