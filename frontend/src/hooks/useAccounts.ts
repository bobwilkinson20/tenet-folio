import { useEffect, useCallback } from "react";
import type { Account } from "../types";
import { accountsApi } from "../api";
import { useFetch } from "./useFetch";

export function useAccounts() {
  const fetchFn = () => accountsApi.list();
  const { data: accounts, loading, error, refetch, setData } = useFetch<Account[]>(
    fetchFn
  );

  useEffect(() => {
    refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Optimistically update a single account in the local state
  const updateAccount = useCallback((id: string, updates: Partial<Account>) => {
    setData((prev) => {
      if (!prev) return [];
      return prev.map((account) =>
        account.id === id ? { ...account, ...updates } : account
      );
    });
  }, [setData]);

  // Remove an account from local state
  const deleteAccount = useCallback((id: string) => {
    setData((prev) => {
      if (!prev) return [];
      return prev.filter((account) => account.id !== id);
    });
  }, [setData]);

  return {
    accounts: accounts ?? [],
    loading,
    error,
    refetch,
    updateAccount,
    deleteAccount,
  };
}

