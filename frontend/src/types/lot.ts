export interface LotDisposal {
  id: string;
  holding_lot_id: string;
  account_id: string;
  security_id: string;
  disposal_date: string;
  quantity: number;
  proceeds_per_unit: number;
  source: "activity" | "inferred" | "initial" | "manual";
  activity_id?: string | null;
  disposal_group_id?: string | null;
  realized_gain_loss?: number | null;
  created_at: string;
}

export interface HoldingLot {
  id: string;
  account_id: string;
  security_id: string;
  ticker: string;
  acquisition_date: string | null;
  cost_basis_per_unit: number;
  original_quantity: number;
  current_quantity: number;
  is_closed: boolean;
  source: "activity" | "inferred" | "initial" | "manual";
  activity_id?: string | null;
  total_cost_basis?: number | null;
  unrealized_gain_loss?: number | null;
  unrealized_gain_loss_percent?: number | null;
  security_name?: string | null;
  disposals: LotDisposal[];
  created_at: string;
  updated_at: string;
}

export interface DisposalAssignment {
  lot_id: string;
  quantity: number;
}

export interface DisposalReassignRequest {
  assignments: DisposalAssignment[];
}

export interface LotBatchUpdate {
  id: string;
  acquisition_date?: string | null;
  cost_basis_per_unit?: number;
  quantity?: number;
}

export interface LotBatchCreate {
  ticker: string;
  acquisition_date: string;
  cost_basis_per_unit: number;
  quantity: number;
}

export interface LotBatchRequest {
  updates: LotBatchUpdate[];
  creates: LotBatchCreate[];
}

export interface LotSummary {
  security_id: string;
  ticker: string;
  security_name?: string | null;
  total_quantity?: number | null;
  lotted_quantity: number;
  lot_count: number;
  total_cost_basis?: number | null;
  unrealized_gain_loss?: number | null;
  realized_gain_loss: number;
  lot_coverage?: number | null;
}
