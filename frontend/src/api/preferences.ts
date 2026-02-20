import { apiClient } from "./client";
import type { PreferenceMap, PreferenceResponse } from "../types/preference";

export const preferencesApi = {
  getAll: () => apiClient.get<PreferenceMap>("/preferences"),
  get: (key: string) =>
    apiClient.get<PreferenceResponse>(`/preferences/${key}`),
  set: (key: string, value: unknown) =>
    apiClient.put<PreferenceResponse>(`/preferences/${key}`, { value }),
  delete: (key: string) => apiClient.delete(`/preferences/${key}`),
};
