import { apiClient } from "./client";

export interface GoogleSheetsReportResponse {
  tab_name: string;
  rows_written: number;
}

export const reportsApi = {
  generateGoogleSheets: () =>
    apiClient.post<GoogleSheetsReportResponse>("/reports/google-sheets"),
};
