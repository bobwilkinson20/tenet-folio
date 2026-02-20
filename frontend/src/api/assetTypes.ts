/**
 * API client for asset type (asset class) operations
 */

import { apiClient } from "./client";
import type {
  AssetType,
  AssetTypeCreate,
  AssetTypeHoldingsDetail,
  AssetTypeListResponse,
  AssetTypeUpdate,
  AssetTypeWithCounts,
} from "@/types/assetType";

export const assetTypeApi = {
  /**
   * List all asset types with total target percentage
   */
  list: () => apiClient.get<AssetTypeListResponse>("/asset-types"),

  /**
   * Get a single asset type by ID with assignment counts
   */
  get: (id: string) => apiClient.get<AssetTypeWithCounts>(`/asset-types/${id}`),

  /**
   * Create a new asset type
   */
  create: (data: AssetTypeCreate) =>
    apiClient.post<AssetType>("/asset-types", data),

  /**
   * Update an asset type
   */
  update: (id: string, data: AssetTypeUpdate) =>
    apiClient.patch<AssetType>(`/asset-types/${id}`, data),

  /**
   * Delete an asset type (fails if has assignments)
   */
  delete: (id: string) => apiClient.delete(`/asset-types/${id}`),

  /**
   * Get holdings classified under a specific asset type
   */
  getHoldings: (id: string) =>
    apiClient.get<AssetTypeHoldingsDetail>(`/asset-types/${id}/holdings`),
};
