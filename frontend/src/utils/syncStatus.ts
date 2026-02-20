/** Minimal interface for sync-status helper functions. */
export interface SyncStatusFields {
  provider_name: string;
  last_sync_status?: string | null;
  last_sync_time?: string | null;
  last_sync_error?: string | null;
  balance_date?: string | null;
  valuation_status?: string | null;
  valuation_date?: string | null;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Never";
  const date = new Date(value);
  return date.toLocaleString();
}

export function formatDateOrDash(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return date.toLocaleString();
}

export const STALE_THRESHOLD_MS = 24 * 60 * 60 * 1000;
export const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

export function getSyncIconState(
  account: SyncStatusFields,
): "green" | "yellow" | "red" | "gray" {
  if (account.provider_name === "Manual") return "gray";
  if (account.last_sync_status === "error") return "red";
  if (account.valuation_status === "missing") return "red";
  if (account.last_sync_status === "skipped") return "yellow";
  if (account.last_sync_status === "stale") {
    if (account.balance_date) {
      const age = Date.now() - new Date(account.balance_date).getTime();
      if (age <= STALE_THRESHOLD_MS) {
        // Would be green, but check valuation
        if (account.valuation_status === "partial" || account.valuation_status === "stale") return "yellow";
        return "green";
      }
    }
    return "yellow";
  }
  if (!account.last_sync_time) return "yellow";
  const age = Date.now() - new Date(account.last_sync_time).getTime();
  if (age > SEVEN_DAYS_MS) return "yellow";
  // Would be green, but check valuation
  if (account.valuation_status === "partial" || account.valuation_status === "stale") return "yellow";
  return "green";
}

export function getSyncTooltip(account: SyncStatusFields): string {
  const lines: string[] = [];
  if (account.provider_name === "Manual") {
    lines.push("Manual account");
    lines.push(`Last updated: ${formatDateOrDash(account.balance_date)}`);
    return lines.join("\n");
  }
  lines.push(`Synced: ${formatDateTime(account.last_sync_time)}`);
  lines.push(`Data as of: ${formatDateOrDash(account.balance_date)}`);
  if (account.last_sync_error) {
    lines.push(account.last_sync_error);
  } else if (account.last_sync_status === "stale") {
    if (account.balance_date) {
      const age = Date.now() - new Date(account.balance_date).getTime();
      if (age <= STALE_THRESHOLD_MS) {
        lines.push("No new data from provider");
      } else {
        lines.push("Data may be outdated");
      }
    } else {
      lines.push("Data may be outdated");
    }
  }
  // Append valuation warnings
  if (account.valuation_status === "missing") {
    lines.push("Valuation data missing \u2014 value shown as $0");
  } else if (account.valuation_status === "partial") {
    lines.push("Some holdings missing valuation data");
  } else if (account.valuation_status === "stale" && account.valuation_date) {
    lines.push(`Valuation data from ${account.valuation_date}`);
  }
  return lines.join("\n");
}
