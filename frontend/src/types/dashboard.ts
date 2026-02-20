export interface AccountSummary {
  id: string;
  name: string;
  provider_name: string;
  institution_name?: string | null;
  value: string; // Decimal comes as string from API
  // Per-account sync status
  last_sync_time: string | null;
  last_sync_status: string | null; // "success" | "failed" | "syncing" | "stale" | "error" | null
  last_sync_error: string | null;
  balance_date: string | null;
  // Per-account valuation health
  valuation_status: "ok" | "partial" | "missing" | "stale" | null;
  valuation_date: string | null; // ISO date (YYYY-MM-DD)
}

export interface AllocationData {
  asset_type_id: string;
  asset_type_name: string;
  asset_type_color: string;
  target_percent: string; // Decimal comes as string from API
  actual_percent: string;
  delta_percent: string;
  value: string;
}

export interface DashboardData {
  total_net_worth: string; // Decimal comes as string from API
  allocation_total: string; // Sum of allocation holdings (may differ from net worth)
  accounts: AccountSummary[];
  allocations: AllocationData[];
  unassigned_count: number;
  unassigned_value: string;
}
