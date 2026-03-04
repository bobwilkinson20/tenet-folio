import { apiClient } from "./client";

export interface PlaidItem {
  id: string;
  item_id: string;
  institution_id: string | null;
  institution_name: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string | null;
}

export const plaidApi = {
  createLinkToken: () =>
    apiClient.post<{ link_token: string }>("/plaid/link-token"),

  exchangeToken: (
    publicToken: string,
    institutionId?: string,
    institutionName?: string,
  ) =>
    apiClient.post<{ item_id: string; institution_name: string | null }>(
      "/plaid/exchange-token",
      {
        public_token: publicToken,
        institution_id: institutionId,
        institution_name: institutionName,
      },
    ),

  listItems: () => apiClient.get<PlaidItem[]>("/plaid/items"),

  removeItem: (itemId: string) =>
    apiClient.delete(`/plaid/items/${itemId}`),

  createUpdateLinkToken: (itemId: string) =>
    apiClient.post<{ link_token: string }>(
      `/plaid/items/${itemId}/update-link-token`,
    ),

  clearItemError: (itemId: string) =>
    apiClient.post<{ status: string; item_id: string }>(
      `/plaid/items/${itemId}/clear-error`,
    ),
};
