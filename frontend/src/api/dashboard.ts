import { apiClient } from "./client";
import type { DashboardData } from "../types/dashboard";

export const dashboardApi = {
  get: (params?: { allocation_only?: boolean; account_ids?: string }) =>
    apiClient.get<DashboardData>("/dashboard", { params }),
};
