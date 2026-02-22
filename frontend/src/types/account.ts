export type AccountType =
  | "taxable"
  | "traditional_ira"
  | "roth_ira"
  | "401k"
  | "roth_401k"
  | "529"
  | "hsa"
  | "charitable"
  | "other";

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  taxable: "Taxable",
  traditional_ira: "Traditional IRA",
  roth_ira: "Roth IRA",
  "401k": "401(k)",
  roth_401k: "Roth 401(k)",
  "529": "529",
  hsa: "HSA",
  charitable: "Charitable",
  other: "Other",
};

export interface Account {
  id: string;
  provider_name: string;
  external_id: string;
  name: string;
  institution_name?: string | null;
  is_active: boolean;
  deactivated_at?: string | null;
  superseded_by_account_id?: string | null;
  superseded_by_name?: string | null;
  account_type?: AccountType | null;
  include_in_allocation: boolean;
  assigned_asset_class_id: string | null;
  created_at: string;
  updated_at: string;
  assigned_asset_class_name?: string | null;
  assigned_asset_class_color?: string | null;
  value?: string | null; // Decimal comes as string from API
  last_sync_time?: string | null;
  last_sync_status?: string | null;
  last_sync_error?: string | null;
  balance_date?: string | null;
}

export interface DeactivateAccountRequest {
  create_closing_snapshot: boolean;
  superseded_by_account_id?: string | null;
}

export interface ManualHoldingInput {
  ticker?: string;
  description?: string;
  quantity?: number;
  price?: number;
  market_value?: number;
  acquisition_date?: string;
  cost_basis_per_unit?: number;
}
