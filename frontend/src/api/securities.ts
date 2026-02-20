/**
 * API client for securities operations
 */

import { apiClient } from "./client";
import type { SecurityWithType, UnassignedResponse } from "@/types/assetType";

export const securitiesApi = {
  /**
   * List all securities with optional filters
   */
  list: (params?: { search?: string; unassigned_only?: boolean }) =>
    apiClient.get<SecurityWithType[]>("/securities", { params }),

  /**
   * Get unassigned securities count and list
   */
  getUnassigned: () =>
    apiClient.get<UnassignedResponse>("/securities/unassigned"),

  /**
   * Update a security's asset type assignment
   */
  updateType: (id: string, asset_type_id: string | null) =>
    apiClient.patch<SecurityWithType>(`/securities/${id}`, {
      manual_asset_class_id: asset_type_id,
    }),
};
