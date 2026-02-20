import { useState, useCallback, useRef } from "react";
import { AxiosError } from "axios";

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: AxiosError | null;
}

export function useFetch<T>(
  fetchFn: () => Promise<{ data: T }>
): FetchState<T> & { refetch: () => Promise<void>; setData: (data: T | ((prev: T | null) => T)) => void } {
  const [state, setState] = useState<FetchState<T>>({
    data: null,
    loading: false,
    error: null,
  });
  const requestIdRef = useRef(0);

  const refetch = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setState((prev) => ({ ...prev, loading: true }));
    try {
      const response = await fetchFn();
      if (requestId === requestIdRef.current) {
        setState({ data: response.data, loading: false, error: null });
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        const error = err instanceof AxiosError ? err : new AxiosError("Unknown error");
        setState({ data: null, loading: false, error });
      }
    }
  }, [fetchFn]);

  const setData = useCallback((data: T | ((prev: T | null) => T)) => {
    setState((prev) => ({
      ...prev,
      data: typeof data === "function" ? (data as (prev: T | null) => T)(prev.data) : data,
    }));
  }, []);

  return {
    ...state,
    refetch,
    setData,
  };
}
