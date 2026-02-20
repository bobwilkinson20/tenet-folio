import { apiClient } from "./client";
import type { Holding, SyncLogEntry } from "../types/sync_session";

export interface SyncSession {
  id: string;
  timestamp: string;
  is_complete: boolean;
  error_message: string | null;
  created_at: string;
  holdings: Holding[];
}

export interface SyncResponse extends SyncSession {
  sync_log: SyncLogEntry[];
}

export const syncApi = {
  trigger: () => apiClient.post<SyncResponse>("/sync"),
};
