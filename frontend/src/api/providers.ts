import { apiClient } from "./client";
import type { ProviderStatus } from "../types/provider";

export const providersApi = {
  list: () => apiClient.get<ProviderStatus[]>("/providers"),
  update: (name: string, isEnabled: boolean) =>
    apiClient.put<ProviderStatus>(`/providers/${name}`, {
      is_enabled: isEnabled,
    }),
};
