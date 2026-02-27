import { apiClient } from "./client";

export interface GoogleSheetsReportResponse {
  tab_name: string;
  rows_written: number;
}

export interface GenerateGoogleSheetsParams {
  allocation_only?: boolean;
}

export const reportsApi = {
  generateGoogleSheets: (params?: GenerateGoogleSheetsParams) =>
    apiClient.post<GoogleSheetsReportResponse>("/reports/google-sheets", null, {
      params,
    }),
};
