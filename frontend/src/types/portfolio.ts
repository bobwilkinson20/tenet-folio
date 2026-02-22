export interface ValuePoint {
  date: string; // ISO date "2025-06-01"
  value: string; // Decimal string "487250.00"
}

export interface SeriesData {
  account_name?: string | null;
  asset_class_name?: string | null;
  asset_class_color?: string | null;
  data_points: ValuePoint[];
}

export interface PortfolioValueHistory {
  start_date: string;
  end_date: string;
  data_points?: ValuePoint[] | null;
  series?: Record<string, SeriesData> | null;
}

export interface PortfolioCostBasis {
  has_lots: boolean;
  lot_count: number;
  coverage_percent: number | null;
  total_cost_basis: string | null;
  total_market_value: string | null;
  total_unrealized_gain_loss: string | null;
  total_realized_gain_loss_ytd: string | null;
}

export interface RealizedGainItem {
  disposal_id: string;
  disposal_date: string;
  ticker: string;
  security_name: string;
  account_name: string;
  quantity: string;
  cost_basis_per_unit: string;
  proceeds_per_unit: string;
  total_cost: string;
  total_proceeds: string;
  gain_loss: string;
  source: string;
}

export interface RealizedGainsReport {
  items: RealizedGainItem[];
  total_realized_gain_loss: string;
  year: number | null;
}

export interface PeriodReturn {
  period: string;
  irr: string | null;
  start_date: string;
  end_date: string;
  has_sufficient_data: boolean;
}

export interface ScopeReturns {
  scope_id: string;
  scope_name: string;
  periods: PeriodReturn[];
  chained_from: string[];
}

export interface PortfolioReturnsResponse {
  portfolio: ScopeReturns | null;
  accounts: ScopeReturns[];
}
