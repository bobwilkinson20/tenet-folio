import { describe, it, expect, vi, afterEach } from "vitest";
import {
  getSyncIconState,
  getSyncTooltip,
  formatDateTime,
  formatDateOrDash,
  SEVEN_DAYS_MS,
} from "@/utils/syncStatus";
import type { SyncStatusFields } from "@/utils/syncStatus";

describe("formatDateTime", () => {
  it("returns 'Never' for null", () => {
    expect(formatDateTime(null)).toBe("Never");
  });

  it("returns 'Never' for undefined", () => {
    expect(formatDateTime(undefined)).toBe("Never");
  });

  it("returns formatted date string for valid ISO string", () => {
    const result = formatDateTime("2026-01-15T10:30:00Z");
    expect(result).toBeTruthy();
    expect(result).not.toBe("Never");
  });
});

describe("formatDateOrDash", () => {
  it("returns '-' for null", () => {
    expect(formatDateOrDash(null)).toBe("-");
  });

  it("returns '-' for undefined", () => {
    expect(formatDateOrDash(undefined)).toBe("-");
  });

  it("returns formatted date string for valid ISO string", () => {
    const result = formatDateOrDash("2026-01-15T10:30:00Z");
    expect(result).toBeTruthy();
    expect(result).not.toBe("-");
  });
});

describe("SEVEN_DAYS_MS", () => {
  it("equals 7 days in milliseconds", () => {
    expect(SEVEN_DAYS_MS).toBe(7 * 24 * 60 * 60 * 1000);
  });
});

describe("getSyncIconState", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns 'gray' for Manual accounts", () => {
    const account: SyncStatusFields = {
      provider_name: "Manual",
      last_sync_status: null,
      last_sync_time: null,
      last_sync_error: null,
      balance_date: null,
    };
    expect(getSyncIconState(account)).toBe("gray");
  });

  it("returns 'red' for error status", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "error",
      last_sync_time: "2026-01-15T10:30:00Z",
      last_sync_error: "Connection failed",
      balance_date: null,
    };
    expect(getSyncIconState(account)).toBe("red");
  });

  it("returns 'green' for stale status with recent balance_date", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "stale",
      last_sync_time: "2026-01-15T10:30:00Z",
      last_sync_error: null,
      balance_date: new Date().toISOString(),
    };
    expect(getSyncIconState(account)).toBe("green");
  });

  it("returns 'yellow' for stale status with old balance_date", () => {
    const oldDate = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "stale",
      last_sync_time: "2026-01-15T10:30:00Z",
      last_sync_error: null,
      balance_date: oldDate,
    };
    expect(getSyncIconState(account)).toBe("yellow");
  });

  it("returns 'yellow' for stale status with no balance_date", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "stale",
      last_sync_time: "2026-01-15T10:30:00Z",
      last_sync_error: null,
      balance_date: null,
    };
    expect(getSyncIconState(account)).toBe("yellow");
  });

  it("returns 'yellow' for skipped status", () => {
    const account: SyncStatusFields = {
      provider_name: "SimpleFIN",
      last_sync_status: "skipped",
      last_sync_time: "2026-01-15T10:30:00Z",
      last_sync_error: "Account not returned by provider",
      balance_date: null,
    };
    expect(getSyncIconState(account)).toBe("yellow");
  });

  it("returns 'yellow' when last_sync_time is null", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: null,
      last_sync_time: null,
      last_sync_error: null,
      balance_date: null,
    };
    expect(getSyncIconState(account)).toBe("yellow");
  });

  it("returns 'yellow' when sync is older than 7 days", () => {
    const oldDate = new Date(Date.now() - 8 * 24 * 60 * 60 * 1000).toISOString();
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "success",
      last_sync_time: oldDate,
      last_sync_error: null,
      balance_date: null,
    };
    expect(getSyncIconState(account)).toBe("yellow");
  });

  it("returns 'green' for recent successful sync", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "success",
      last_sync_time: new Date().toISOString(),
      last_sync_error: null,
      balance_date: null,
    };
    expect(getSyncIconState(account)).toBe("green");
  });
});

describe("getSyncTooltip", () => {
  it("shows 'Manual account' and last updated for Manual accounts", () => {
    const account: SyncStatusFields = {
      provider_name: "Manual",
      last_sync_status: null,
      last_sync_time: null,
      last_sync_error: null,
      balance_date: "2026-01-15T00:00:00Z",
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("Manual account");
    expect(tooltip).toContain("Last updated:");
    expect(tooltip).not.toContain("-");
  });

  it("shows dash for Manual accounts with no balance_date", () => {
    const account: SyncStatusFields = {
      provider_name: "Manual",
      last_sync_status: null,
      last_sync_time: null,
      last_sync_error: null,
      balance_date: null,
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("Manual account");
    expect(tooltip).toContain("Last updated: -");
  });

  it("shows sync time and data date for non-manual accounts", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "success",
      last_sync_time: "2026-01-29T10:30:00Z",
      last_sync_error: null,
      balance_date: "2026-01-28T12:00:00Z",
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("Synced:");
    expect(tooltip).toContain("Data as of:");
  });

  it("includes error message when present", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "error",
      last_sync_time: "2026-01-29T10:30:00Z",
      last_sync_error: "Connection to Vanguard may need attention",
      balance_date: null,
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("Connection to Vanguard may need attention");
  });

  it("shows 'No new data from provider' for stale status with recent balance_date", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "stale",
      last_sync_time: "2026-01-29T10:30:00Z",
      last_sync_error: null,
      balance_date: new Date().toISOString(),
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("No new data from provider");
    expect(tooltip).not.toContain("Data may be outdated");
  });

  it("shows 'Data may be outdated' for stale status with old balance_date", () => {
    const oldDate = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "stale",
      last_sync_time: "2026-01-29T10:30:00Z",
      last_sync_error: null,
      balance_date: oldDate,
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("Data may be outdated");
  });

  it("shows 'Data may be outdated' for stale status with no balance_date", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "stale",
      last_sync_time: "2026-01-29T10:30:00Z",
      last_sync_error: null,
      balance_date: null,
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("Data may be outdated");
  });

  it("shows 'Never' when last_sync_time is null", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: null,
      last_sync_time: null,
      last_sync_error: null,
      balance_date: null,
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("Synced: Never");
  });
});

describe("getSyncIconState with valuation_status", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("missing valuation promotes to red", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "success",
      last_sync_time: new Date().toISOString(),
      last_sync_error: null,
      balance_date: null,
      valuation_status: "missing",
    };
    expect(getSyncIconState(account)).toBe("red");
  });

  it("partial valuation promotes green to yellow", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "success",
      last_sync_time: new Date().toISOString(),
      last_sync_error: null,
      balance_date: null,
      valuation_status: "partial",
    };
    expect(getSyncIconState(account)).toBe("yellow");
  });

  it("stale valuation promotes green to yellow", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "success",
      last_sync_time: new Date().toISOString(),
      last_sync_error: null,
      balance_date: null,
      valuation_status: "stale",
    };
    expect(getSyncIconState(account)).toBe("yellow");
  });

  it("valuation doesn't override sync error red", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "error",
      last_sync_time: new Date().toISOString(),
      last_sync_error: "Connection failed",
      balance_date: null,
      valuation_status: "ok",
    };
    expect(getSyncIconState(account)).toBe("red");
  });

  it("valuation doesn't affect Manual accounts", () => {
    const account: SyncStatusFields = {
      provider_name: "Manual",
      last_sync_status: null,
      last_sync_time: null,
      last_sync_error: null,
      balance_date: null,
      valuation_status: "missing",
    };
    expect(getSyncIconState(account)).toBe("gray");
  });
});

describe("getSyncTooltip with valuation_status", () => {
  it("tooltip includes valuation warning text for missing", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "success",
      last_sync_time: new Date().toISOString(),
      last_sync_error: null,
      balance_date: null,
      valuation_status: "missing",
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("Valuation data missing");
    expect(tooltip).toContain("$0");
  });

  it("tooltip includes warning for partial valuation", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "success",
      last_sync_time: new Date().toISOString(),
      last_sync_error: null,
      balance_date: null,
      valuation_status: "partial",
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("Some holdings missing valuation data");
  });

  it("tooltip includes date for stale valuation", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "success",
      last_sync_time: new Date().toISOString(),
      last_sync_error: null,
      balance_date: null,
      valuation_status: "stale",
      valuation_date: "2026-01-10",
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).toContain("Valuation data from 2026-01-10");
  });

  it("no valuation warning for ok status", () => {
    const account: SyncStatusFields = {
      provider_name: "SnapTrade",
      last_sync_status: "success",
      last_sync_time: new Date().toISOString(),
      last_sync_error: null,
      balance_date: null,
      valuation_status: "ok",
    };
    const tooltip = getSyncTooltip(account);
    expect(tooltip).not.toContain("Valuation");
    expect(tooltip).not.toContain("valuation");
  });
});
