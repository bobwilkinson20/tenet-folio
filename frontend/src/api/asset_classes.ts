import { apiClient } from "./client";
import type { AssetClass } from "../types";

export const assetClassesApi = {
  list: () => apiClient.get<AssetClass[]>("/asset-classes"),
  get: (id: string) => apiClient.get<AssetClass>(`/asset-classes/${id}`),
  create: (data: { name: string; target_percent: number }) =>
    apiClient.post<AssetClass>("/asset-classes", data),
};
