import { apiClient } from "./client";

export interface SnapTradeConnection {
  authorization_id: string;
  brokerage_name: string;
  name: string;
  disabled: boolean;
  disabled_date: string | null;
  error_message: string | null;
}

export const snaptradeApi = {
  listConnections: () =>
    apiClient.get<SnapTradeConnection[]>("/snaptrade/connections"),

  getConnectUrl: () =>
    apiClient.post<{ redirect_url: string }>("/snaptrade/connect-url"),

  removeConnection: (authorizationId: string) =>
    apiClient.delete(`/snaptrade/connections/${authorizationId}`),

  refreshConnection: (authorizationId: string) =>
    apiClient.post<{ redirect_url: string; authorization_id: string }>(
      `/snaptrade/connections/${authorizationId}/refresh`,
    ),
};
