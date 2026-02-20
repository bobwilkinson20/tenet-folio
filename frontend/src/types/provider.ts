export interface ProviderStatus {
  name: string;
  has_credentials: boolean;
  is_enabled: boolean;
  account_count: number;
  last_sync_time: string | null;
}
