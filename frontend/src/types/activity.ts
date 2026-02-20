export interface Activity {
  id: string;
  account_id: string;
  provider_name: string;
  external_id: string;
  activity_date: string;
  settlement_date: string | null;
  type: string;
  description: string | null;
  ticker: string | null;
  units: string | null;
  price: string | null;
  amount: string | null;
  currency: string | null;
  fee: string | null;
  is_reviewed: boolean;
  notes: string | null;
  user_modified: boolean;
  created_at: string;
}

export interface CashFlowAccountSummary {
  account_id: string;
  account_name: string;
  total_inflows: string;
  total_outflows: string;
  net_flow: string;
  activity_count: number;
  unreviewed_count: number;
}

export interface ActivityCreate {
  activity_date: string;
  type: string;
  amount?: number;
  description?: string;
  ticker?: string;
  notes?: string;
}

export interface ActivityUpdate {
  type?: string;
  amount?: number;
  notes?: string;
  activity_date?: string;
}
