/**
 * Asset Type (Asset Class) types
 */

export interface AssetType {
  id: string;
  name: string;
  color: string;
  target_percent: number;
  created_at: string;
  updated_at: string;
}

export interface AssetTypeWithCounts extends AssetType {
  security_count: number;
  account_count: number;
}

export interface AssetTypeCreate {
  name: string;
  color: string;
}

export interface AssetTypeUpdate {
  name?: string;
  color?: string;
  target_percent?: number;
}

export interface AssetTypeListResponse {
  items: AssetType[];
  total_target_percent: number;
}

export interface SecurityWithType {
  id: string;
  ticker: string;
  name: string | null;
  manual_asset_class_id: string | null;
  created_at: string;
  updated_at: string;
  asset_type_id: string | null;
  asset_type_name: string | null;
  asset_type_color: string | null;
}

export interface UnassignedResponse {
  count: number;
  items: SecurityWithType[];
}

export interface AllocationTarget {
  asset_type_id: string;
  target_percent: number;
}

export interface AllocationTargetResponse {
  allocations: AllocationTarget[];
  total_percent: number;
  is_valid: boolean;
}

export interface AllocationActual {
  asset_type_id: string;
  asset_type_name: string;
  asset_type_color: string;
  target_percent: number;
  actual_percent: number;
  delta_percent: number;
  value: number;
}

export interface AssetTypeHolding {
  holding_id: string;
  account_id: string;
  account_name: string;
  ticker: string;
  security_name: string | null;
  market_value: string; // Decimal comes as string from API
}

export interface AssetTypeHoldingsDetail {
  asset_type_id: string;
  asset_type_name: string;
  asset_type_color: string;
  total_value: string; // Decimal comes as string from API
  holdings: AssetTypeHolding[];
}

// Default color palette
export const DEFAULT_COLORS = [
  "#3B82F6", // Blue
  "#10B981", // Green
  "#F59E0B", // Amber
  "#EF4444", // Red
  "#8B5CF6", // Purple
  "#EC4899", // Pink
  "#06B6D4", // Cyan
  "#F97316", // Orange
];

/**
 * Check if a color is in the default palette
 */
export function isDefaultColor(color: string): boolean {
  return DEFAULT_COLORS.includes(color.toUpperCase()) ||
    DEFAULT_COLORS.includes(color.toLowerCase()) ||
    DEFAULT_COLORS.includes(color);
}
