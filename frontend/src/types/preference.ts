export type PreferenceMap = Record<string, unknown>;

export interface PreferenceResponse {
  key: string;
  value: unknown;
  updated_at: string;
}
