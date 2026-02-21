import { apiClient } from "./client";

export interface PlaidItem {
  id: string;
  item_id: string;
  institution_id: string | null;
  institution_name: string | null;
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
};
