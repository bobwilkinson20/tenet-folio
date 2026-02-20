export interface Holding {
  id: string;
  account_snapshot_id: string;
  security_id?: string | null;
  ticker: string;
  quantity: number;
  snapshot_price: number;
  snapshot_value: number;
  created_at: string;
  security_name?: string | null;
  market_price?: string | null;
  market_value?: string | null;
  cost_basis?: string | null;
  gain_loss?: string | null;
  gain_loss_percent?: string | null;
  lot_coverage?: string | null;
  lot_count?: number | null;
  realized_gain_loss?: string | null;
}

export interface SyncLogEntry {
  id: string;
  provider_name: string;
  status: "success" | "failed" | "partial";
  error_messages: string[] | null;
  accounts_synced: number;
  created_at: string;
}
