import { useEffect, useCallback } from "react";
import type { DashboardData } from "../types";
import { dashboardApi } from "../api";
import { useFetch } from "./useFetch";
import { usePortfolioContext } from "../context";

export function useDashboard(
  allocationOnly = false,
  enabled = true,
  selectedAccountIds: string[] | null = null,
) {
  const accountIdsParam = selectedAccountIds?.join(",") || undefined;
  const fetchFn = useCallback(
    () => {
      const params: { allocation_only?: boolean; account_ids?: string } = {};
      if (allocationOnly) params.allocation_only = true;
      if (accountIdsParam) params.account_ids = accountIdsParam;
      return dashboardApi.get(
        Object.keys(params).length > 0 ? params : undefined
      );
    },
    [allocationOnly, accountIdsParam]
  );
  const { data, loading, error, refetch } = useFetch<DashboardData>(fetchFn);
  const { dashboardStale, setDashboardStale } = usePortfolioContext();

  useEffect(() => {
    if (enabled) {
      refetch();
    }
  }, [refetch, enabled]);

  // Refetch when dashboard data becomes stale (e.g., after allocation changes)
  useEffect(() => {
    if (dashboardStale) {
      refetch();
      setDashboardStale(false);
    }
  }, [dashboardStale, refetch, setDashboardStale]);

  return {
    dashboard: data,
    loading,
    error,
    refetch,
  };
}
