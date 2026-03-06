import { apiClient } from "./client";
import type {
  GoogleSheetsCredentialStatus,
  ReportSheetTarget,
  ReportType,
} from "@/types/report";

export interface GoogleSheetsReportResponse {
  tab_name: string;
  rows_written: number;
}

export interface GenerateGoogleSheetsParams {
  target_id: string;
  allocation_only?: boolean;
}

export interface CreateTargetRequest {
  report_type: string;
  spreadsheet_id: string;
  display_name?: string;
  config?: Record<string, string>;
}

export interface UpdateTargetRequest {
  display_name?: string;
  config?: Record<string, string>;
}

export const reportsApi = {
  // Report generation
  generateGoogleSheets: (params: GenerateGoogleSheetsParams) =>
    apiClient.post<GoogleSheetsReportResponse>("/reports/google-sheets", null, {
      params,
    }),

  // Credentials
  getCredentialStatus: () =>
    apiClient.get<GoogleSheetsCredentialStatus>("/reports/config/credentials"),

  setCredentials: (credentialsJson: string) =>
    apiClient.post<GoogleSheetsCredentialStatus>("/reports/config/credentials", {
      credentials_json: credentialsJson,
    }),

  removeCredentials: () =>
    apiClient.delete("/reports/config/credentials"),

  // Report types
  getReportTypes: () =>
    apiClient.get<ReportType[]>("/reports/config/types"),

  // Sheet targets
  getTargets: (reportType?: string) =>
    apiClient.get<ReportSheetTarget[]>("/reports/config/targets", {
      params: reportType ? { report_type: reportType } : undefined,
    }),

  createTarget: (data: CreateTargetRequest) =>
    apiClient.post<ReportSheetTarget>("/reports/config/targets", data),

  updateTarget: (id: string, data: UpdateTargetRequest) =>
    apiClient.put<ReportSheetTarget>(`/reports/config/targets/${id}`, data),

  deleteTarget: (id: string) =>
    apiClient.delete(`/reports/config/targets/${id}`),
};
