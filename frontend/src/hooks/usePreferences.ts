import { useState, useEffect, useRef, useCallback } from "react";
import { preferencesApi } from "../api/preferences";
import type { PreferenceMap } from "../types/preference";

export function usePreferences() {
  const [prefs, setPrefs] = useState<PreferenceMap>({});
  const [loading, setLoading] = useState(true);
  const loadedRef = useRef(false);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;

    preferencesApi
      .getAll()
      .then((res) => setPrefs(res.data))
      .catch((err) => {
        console.error("Failed to load preferences:", err);
      })
      .finally(() => setLoading(false));
  }, []);

  const getPreference = useCallback(
    <T>(key: string, defaultValue: T): T => {
      if (key in prefs) {
        return prefs[key] as T;
      }
      return defaultValue;
    },
    [prefs],
  );

  const setPreference = useCallback((key: string, value: unknown) => {
    setPrefs((prev) => {
      const previousValue = prev[key];

      preferencesApi.set(key, value).catch((err) => {
        console.error("Failed to save preference:", err);
        setPrefs((current) => ({ ...current, [key]: previousValue }));
      });

      return { ...prev, [key]: value };
    });
  }, []);

  return { loading, getPreference, setPreference };
}
