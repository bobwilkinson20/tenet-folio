import { useEffect, useCallback } from "react";
import type { Account, Activity } from "../types";
import type { Holding } from "../types/sync_session";
import { accountsApi } from "../api";
import { useFetch } from "./useFetch";

interface AccountDetailsData {
  account: Account;
  holdings: Holding[];
  activities: Activity[];
}

export function useAccountDetails(id: string | undefined) {
  const fetchFn = useCallback(async () => {
    if (!id) throw new Error("No account ID");
    const [accRes, holdRes, actRes] = await Promise.all([
      accountsApi.get(id),
      accountsApi.getHoldings(id),
      accountsApi.getActivities(id),
    ]);
    return {
      data: {
        account: accRes.data,
        holdings: holdRes.data,
        activities: actRes.data,
      },
    };
  }, [id]);

  const { data, loading, error, refetch, setData } =
    useFetch<AccountDetailsData>(fetchFn);

  useEffect(() => {
    if (id) {
      refetch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const refetchHoldings = useCallback(async () => {
    if (!id) return;
    try {
      const holdRes = await accountsApi.getHoldings(id);
      setData((prev) => {
        if (!prev) return prev as unknown as AccountDetailsData;
        return { ...prev, holdings: holdRes.data };
      });
    } catch (err) {
      console.error("Failed to refresh holdings:", err);
    }
  }, [id, setData]);

  return {
    account: data?.account ?? null,
    holdings: data?.holdings ?? [],
    activities: data?.activities ?? [],
    loading,
    error,
    refetchHoldings,
  };
}
