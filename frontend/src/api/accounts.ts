import { apiClient } from "./client";
import type {
  Account,
  Activity,
  ActivityCreate,
  ActivityUpdate,
  DeactivateAccountRequest,
  DisposalReassignRequest,
  HoldingLot,
  LotBatchRequest,
  LotDisposal,
  LotSummary,
  ManualHoldingInput,
} from "../types";
import type { Holding } from "../types/sync_session";

export const accountsApi = {
  list: () => apiClient.get<Account[]>("/accounts"),
  get: (id: string) => apiClient.get<Account>(`/accounts/${id}`),
  getHoldings: (id: string) => apiClient.get<Holding[]>(`/accounts/${id}/holdings`),
  getActivities: (
    id: string,
    params?: {
      limit?: number;
      offset?: number;
      activity_type?: string;
      reviewed?: boolean;
      start_date?: string;
      end_date?: string;
    },
  ) => apiClient.get<Activity[]>(`/accounts/${id}/activities`, { params }),
  createActivity: (accountId: string, data: ActivityCreate) =>
    apiClient.post<Activity>(`/accounts/${accountId}/activities`, data),
  updateActivity: (accountId: string, activityId: string, data: ActivityUpdate) =>
    apiClient.patch<Activity>(`/accounts/${accountId}/activities/${activityId}`, data),
  deleteActivity: (accountId: string, activityId: string) =>
    apiClient.delete(`/accounts/${accountId}/activities/${activityId}`),
  markActivitiesReviewed: (accountId: string, activityIds: string[]) =>
    apiClient.post<{ updated_count: number }>(
      `/accounts/${accountId}/activities/mark-reviewed`,
      { activity_ids: activityIds },
    ),
  create: (data: { provider_name: string; external_id: string; name: string }) =>
    apiClient.post<Account>("/accounts", data),
  update: (id: string, data: Partial<Account>) =>
    apiClient.patch<Account>(`/accounts/${id}`, data),
  createManual: (data: { name: string; institution_name?: string }) =>
    apiClient.post<Account>("/accounts/manual", data),
  addHolding: (accountId: string, data: ManualHoldingInput) =>
    apiClient.post<Holding>(`/accounts/${accountId}/holdings`, data),
  updateHolding: (accountId: string, holdingId: string, data: ManualHoldingInput) =>
    apiClient.put<Holding>(`/accounts/${accountId}/holdings/${holdingId}`, data),
  deactivate: (id: string, data: DeactivateAccountRequest) =>
    apiClient.post<Account>(`/accounts/${id}/deactivate`, data),
  delete: (id: string) => apiClient.delete(`/accounts/${id}`),
  deleteHolding: (accountId: string, holdingId: string) =>
    apiClient.delete(`/accounts/${accountId}/holdings/${holdingId}`),

  // Lot management
  getLots: (accountId: string) =>
    apiClient.get<HoldingLot[]>(`/accounts/${accountId}/lots`),
  getLotSummaries: (accountId: string) =>
    apiClient.get<LotSummary[]>(`/accounts/${accountId}/lots/summary`),
  getLotsBySecurity: (accountId: string, securityId: string) =>
    apiClient.get<HoldingLot[]>(
      `/accounts/${accountId}/lots/by-security/${securityId}`,
    ),
  createLot: (
    accountId: string,
    data: { ticker: string; acquisition_date: string; cost_basis_per_unit: number; quantity: number },
  ) => apiClient.post<HoldingLot>(`/accounts/${accountId}/lots`, data),
  updateLot: (
    accountId: string,
    lotId: string,
    data: { acquisition_date?: string; cost_basis_per_unit?: number; quantity?: number },
  ) => apiClient.put<HoldingLot>(`/accounts/${accountId}/lots/${lotId}`, data),
  deleteLot: (accountId: string, lotId: string) =>
    apiClient.delete(`/accounts/${accountId}/lots/${lotId}`),
  saveLotsBatch: (accountId: string, securityId: string, data: LotBatchRequest) =>
    apiClient.put<HoldingLot[]>(
      `/accounts/${accountId}/lots/by-security/${securityId}/batch`,
      data,
    ),
  reassignDisposals: (
    accountId: string,
    disposalGroupId: string,
    data: DisposalReassignRequest,
  ) =>
    apiClient.put<LotDisposal[]>(
      `/accounts/${accountId}/lots/disposals/${disposalGroupId}/reassign`,
      data,
    ),
};
