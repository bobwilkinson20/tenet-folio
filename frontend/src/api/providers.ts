import { apiClient } from "./client";
import type {
  ProviderSetupField,
  ProviderSetupResponse,
  ProviderStatus,
} from "../types/provider";

export const providersApi = {
  list: () => apiClient.get<ProviderStatus[]>("/providers"),
  update: (name: string, isEnabled: boolean) =>
    apiClient.put<ProviderStatus>(`/providers/${name}`, {
      is_enabled: isEnabled,
    }),
  getSetupInfo: (name: string) =>
    apiClient.get<ProviderSetupField[]>(`/providers/${name}/setup-info`),
  setup: (name: string, credentials: Record<string, string>) =>
    apiClient.post<ProviderSetupResponse>(`/providers/${name}/setup`, {
      credentials,
    }),
  removeCredentials: (name: string) =>
    apiClient.delete<ProviderSetupResponse>(`/providers/${name}/credentials`),
};
