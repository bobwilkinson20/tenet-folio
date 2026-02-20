/**
 * API client for portfolio operations
 */

import { apiClient } from "./client";
import type {
  AllocationTarget,
  AllocationTargetResponse,
} from "@/types/assetType";
import type {
  PortfolioCostBasis,
  PortfolioReturnsResponse,
  PortfolioValueHistory,
  RealizedGainsReport,
} from "@/types/portfolio";
import type { CashFlowAccountSummary } from "@/types/activity";

export const portfolioApi = {
  /**
   * Get current target allocation
   */
  getAllocation: () =>
    apiClient.get<AllocationTargetResponse>("/portfolio/allocation"),

  /**
   * Update target allocation (must sum to 100%)
   */
  updateAllocation: (allocations: AllocationTarget[]) =>
    apiClient.put<AllocationTargetResponse>("/portfolio/allocation", {
      allocations,
    }),

  /**
   * Get portfolio value history time series
   */
  getValueHistory: (params?: {
    start?: string;
    end?: string;
    group_by?: "total" | "account" | "asset_class";
    allocation_only?: boolean;
    account_ids?: string;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.start) searchParams.set("start", params.start);
    if (params?.end) searchParams.set("end", params.end);
    if (params?.group_by) searchParams.set("group_by", params.group_by);
    if (params?.allocation_only) searchParams.set("allocation_only", "true");
    if (params?.account_ids) searchParams.set("account_ids", params.account_ids);
    const qs = searchParams.toString();
    return apiClient.get<PortfolioValueHistory>(
      `/portfolio/value-history${qs ? `?${qs}` : ""}`
    );
  },

  /**
   * Get portfolio-wide cost basis summary
   */
  getCostBasis: (params?: { account_ids?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.account_ids) searchParams.set("account_ids", params.account_ids);
    const qs = searchParams.toString();
    return apiClient.get<PortfolioCostBasis>(
      `/portfolio/cost-basis${qs ? `?${qs}` : ""}`
    );
  },

  /**
   * Get realized gains report with optional year filter
   */
  getRealizedGains: (params?: { year?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.year != null) searchParams.set("year", String(params.year));
    const qs = searchParams.toString();
    return apiClient.get<RealizedGainsReport>(
      `/portfolio/realized-gains${qs ? `?${qs}` : ""}`
    );
  },

  getReturns: (params?: {
    scope?: string;
    periods?: string;
    include_inactive?: boolean;
    account_ids?: string;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.scope) searchParams.set("scope", params.scope);
    if (params?.periods) searchParams.set("periods", params.periods);
    if (params?.include_inactive) searchParams.set("include_inactive", "true");
    if (params?.account_ids) searchParams.set("account_ids", params.account_ids);
    const qs = searchParams.toString();
    return apiClient.get<PortfolioReturnsResponse>(
      `/portfolio/returns${qs ? `?${qs}` : ""}`
    );
  },

  getCashFlowSummary: (params?: {
    start_date?: string;
    end_date?: string;
    include_inactive?: boolean;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.start_date) searchParams.set("start_date", params.start_date);
    if (params?.end_date) searchParams.set("end_date", params.end_date);
    if (params?.include_inactive) searchParams.set("include_inactive", "true");
    const qs = searchParams.toString();
    return apiClient.get<CashFlowAccountSummary[]>(
      `/portfolio/cashflow-summary${qs ? `?${qs}` : ""}`
    );
  },
};
