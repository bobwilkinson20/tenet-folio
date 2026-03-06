export interface ReportTypeConfigField {
  key: string;
  label: string;
  help_text?: string;
  required?: boolean;
  default?: string;
}

export interface ReportType {
  id: string;
  display_name: string;
  description: string;
  config_fields: ReportTypeConfigField[];
}

export interface ReportSheetTarget {
  id: string;
  report_type: string;
  spreadsheet_id: string;
  display_name: string;
  config: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface GoogleSheetsCredentialStatus {
  configured: boolean;
  service_account_email: string | null;
}
