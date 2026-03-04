import { apiClient } from "./client";

export interface SchwabAuthUrlResponse {
  authorization_url: string;
  state: string;
}

export interface SchwabTokenExchangeResponse {
  message: string;
  account_count: number;
}

export interface SchwabTokenStatus {
  status: "valid" | "expiring_soon" | "expired" | "no_token" | "no_credentials";
  message: string;
  expires_at: string | null;
  days_remaining: number | null;
}

export const schwabApi = {
  createAuthUrl: () =>
    apiClient.post<SchwabAuthUrlResponse>("/schwab/auth-url"),

  exchangeToken: (state: string, receivedUrl: string) =>
    apiClient.post<SchwabTokenExchangeResponse>("/schwab/exchange-token", {
      state,
      received_url: receivedUrl,
    }),

  getTokenStatus: () =>
    apiClient.get<SchwabTokenStatus>("/schwab/token-status"),
};
