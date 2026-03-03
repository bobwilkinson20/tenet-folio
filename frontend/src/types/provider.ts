export interface ProviderStatus {
  name: string;
  has_credentials: boolean;
  is_enabled: boolean;
  account_count: number;
  last_sync_time: string | null;
  supports_setup: boolean;
}

export interface ProviderSetupField {
  key: string;
  label: string;
  help_text: string;
  input_type: "text" | "textarea" | "password" | "select";
  options?: { value: string; label: string }[];
}

export interface ProviderSetupResponse {
  provider: string;
  message: string;
  warnings: string[];
}
