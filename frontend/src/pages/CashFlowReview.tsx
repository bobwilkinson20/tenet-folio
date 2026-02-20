import { useState, useEffect, useCallback, useMemo } from "react";
import { accountsApi } from "@/api/accounts";
import { portfolioApi } from "@/api/portfolio";
import { usePreferences } from "@/hooks";
import { CashFlowFilterBar } from "@/components/cashflows/CashFlowFilterBar";
import { AccountSummaryRow } from "@/components/cashflows/AccountSummaryRow";
import { ActivityTable } from "@/components/cashflows/ActivityTable";
import { AddActivityModal } from "@/components/cashflows/AddActivityModal";
import type { Activity } from "@/types";
import type { CashFlowAccountSummary } from "@/types/activity";

export function CashFlowReviewPage() {
  const { getPreference, setPreference } = usePreferences();

  // Filters
  const [unreviewedOnly, setUnreviewedOnly] = useState(true);
  const [hideInactive, setHideInactive] = useState(true);
  const [hideZeroNet, setHideZeroNet] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  // Data
  const [summaries, setSummaries] = useState<CashFlowAccountSummary[]>([]);
  const [loadingSummary, setLoadingSummary] = useState(true);

  // Expanded accounts with lazy-loaded activities
  const [expandedAccounts, setExpandedAccounts] = useState<Set<string>>(new Set());
  const [accountActivities, setAccountActivities] = useState<Map<string, Activity[]>>(new Map());
  const [loadingActivities, setLoadingActivities] = useState<Set<string>>(new Set());

  // Bulk operations
  const [markingReviewed, setMarkingReviewed] = useState(false);

  // Modal
  const [addModalAccountId, setAddModalAccountId] = useState<string | null>(null);

  // Load preferences
  useEffect(() => {
    setUnreviewedOnly(getPreference("cashflows.hideReviewed", true) as boolean);
    setHideInactive(getPreference("cashflows.hideInactive", true) as boolean);
    setHideZeroNet(getPreference("cashflows.hideZeroNet", false) as boolean);
  }, [getPreference]);

  const handleUnreviewedOnlyChange = (value: boolean) => {
    setUnreviewedOnly(value);
    setPreference("cashflows.hideReviewed", value);
    setAccountActivities(new Map());
  };

  const handleHideInactiveChange = (value: boolean) => {
    setHideInactive(value);
    setPreference("cashflows.hideInactive", value);
  };

  const handleHideZeroNetChange = (value: boolean) => {
    setHideZeroNet(value);
    setPreference("cashflows.hideZeroNet", value);
  };

  // Load summaries on mount and filter change
  const fetchSummaries = useCallback(async () => {
    setLoadingSummary(true);
    try {
      const params: {
        start_date?: string;
        end_date?: string;
        include_inactive?: boolean;
      } = {};
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      if (!hideInactive) params.include_inactive = true;
      const res = await portfolioApi.getCashFlowSummary(params);
      setSummaries(res.data);
    } finally {
      setLoadingSummary(false);
    }
  }, [startDate, endDate, hideInactive]);

  useEffect(() => {
    fetchSummaries();
  }, [fetchSummaries]);

  // Apply client-side filters and sort by |net flow| descending
  const filteredSummaries = useMemo(() => {
    let result = summaries;
    if (hideZeroNet) {
      result = result.filter((s) => parseFloat(s.net_flow) !== 0);
    }
    return [...result].sort(
      (a, b) => Math.abs(parseFloat(b.net_flow)) - Math.abs(parseFloat(a.net_flow)),
    );
  }, [summaries, hideZeroNet]);

  // Fetch activities when expanding an account
  const fetchActivities = useCallback(
    async (accountId: string) => {
      setLoadingActivities((prev) => new Set(prev).add(accountId));
      try {
        const params: {
          limit: number;
          reviewed?: boolean;
          start_date?: string;
          end_date?: string;
        } = { limit: 500 };
        if (unreviewedOnly) params.reviewed = false;
        if (startDate) params.start_date = startDate;
        if (endDate) params.end_date = endDate;

        const res = await accountsApi.getActivities(accountId, params);
        setAccountActivities((prev) => new Map(prev).set(accountId, res.data));
      } finally {
        setLoadingActivities((prev) => {
          const next = new Set(prev);
          next.delete(accountId);
          return next;
        });
      }
    },
    [unreviewedOnly, startDate, endDate],
  );

  const toggleAccount = (accountId: string) => {
    setExpandedAccounts((prev) => {
      const next = new Set(prev);
      if (next.has(accountId)) {
        next.delete(accountId);
      } else {
        next.add(accountId);
        // Fetch activities if not already cached
        if (!accountActivities.has(accountId)) {
          fetchActivities(accountId);
        }
      }
      return next;
    });
  };

  const handleActivityChanged = (accountId: string) => {
    fetchActivities(accountId);
    fetchSummaries();
  };

  const handleActivityUpdated = (accountId: string, updated: Activity) => {
    // Patch the activity in-place without refetching (avoids scroll jump)
    setAccountActivities((prev) => {
      const activities = prev.get(accountId);
      if (!activities) return prev;
      const next = new Map(prev);
      next.set(
        accountId,
        activities.map((a) => (a.id === updated.id ? updated : a)),
      );
      return next;
    });
    // Refresh summaries in background (type/amount changes may affect totals)
    fetchSummaries();
  };

  // Mark All as Reviewed
  const totalUnreviewed = filteredSummaries.reduce((n, s) => n + s.unreviewed_count, 0);

  const handleMarkAllReviewed = async () => {
    if (totalUnreviewed === 0) return;
    if (!window.confirm(`Mark ${totalUnreviewed} activities as reviewed?`)) return;

    setMarkingReviewed(true);
    try {
      // For each account with unreviewed activities, gather IDs and call API
      for (const summary of filteredSummaries) {
        if (summary.unreviewed_count === 0) continue;

        // Load unreviewed activities for this account if not already cached
        let activities = accountActivities.get(summary.account_id);
        if (!activities) {
          const params: {
            limit: number;
            reviewed: boolean;
            start_date?: string;
            end_date?: string;
          } = { limit: 500, reviewed: false };
          if (startDate) params.start_date = startDate;
          if (endDate) params.end_date = endDate;
          const res = await accountsApi.getActivities(summary.account_id, params);
          activities = res.data;
        }

        const unreviewedIds = activities
          .filter((a) => !a.is_reviewed)
          .map((a) => a.id);

        if (unreviewedIds.length > 0) {
          await accountsApi.markActivitiesReviewed(summary.account_id, unreviewedIds);
        }
      }

      // Refresh: clear cache, refetch summaries, then refetch expanded accounts
      setAccountActivities(new Map());
      await fetchSummaries();
      for (const accountId of expandedAccounts) {
        fetchActivities(accountId);
      }
    } finally {
      setMarkingReviewed(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Cash Flow Review</h1>
      </div>

      {/* Filters */}
      <CashFlowFilterBar
        unreviewedOnly={unreviewedOnly}
        onUnreviewedOnlyChange={handleUnreviewedOnlyChange}
        hideInactive={hideInactive}
        onHideInactiveChange={handleHideInactiveChange}
        hideZeroNet={hideZeroNet}
        onHideZeroNetChange={handleHideZeroNetChange}
        startDate={startDate}
        endDate={endDate}
        onStartDateChange={(v) => {
          setStartDate(v);
          setAccountActivities(new Map());
        }}
        onEndDateChange={(v) => {
          setEndDate(v);
          setAccountActivities(new Map());
        }}
      />

      {/* Actions */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleMarkAllReviewed}
          disabled={totalUnreviewed === 0 || markingReviewed}
          className="px-4 py-2 bg-tf-accent-primary text-tf-text-primary rounded-lg text-sm font-medium hover:bg-tf-accent-hover transition disabled:opacity-50 disabled:cursor-not-allowed"
          data-testid="mark-all-reviewed"
        >
          {markingReviewed ? "Marking..." : `Mark All as Reviewed (${totalUnreviewed})`}
        </button>
      </div>

      {/* Account summaries */}
      {loadingSummary && summaries.length === 0 ? (
        <div className="flex items-center justify-center h-32">
          <p className="text-tf-text-tertiary">Loading...</p>
        </div>
      ) : filteredSummaries.length === 0 ? (
        <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl p-12 text-center">
          <p className="text-tf-text-tertiary">No cash flow activities found.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredSummaries.map((summary) => (
            <AccountSummaryRow
              key={summary.account_id}
              summary={summary}
              isExpanded={expandedAccounts.has(summary.account_id)}
              onToggle={() => toggleAccount(summary.account_id)}
            >
              <ActivityTable
                accountId={summary.account_id}
                activities={accountActivities.get(summary.account_id) ?? []}
                loading={loadingActivities.has(summary.account_id)}
                onActivityUpdated={(updated) => handleActivityUpdated(summary.account_id, updated)}
                onActivityDeleted={() => handleActivityChanged(summary.account_id)}
                onAddActivity={() => setAddModalAccountId(summary.account_id)}
              />
            </AccountSummaryRow>
          ))}
        </div>
      )}

      {/* Add Activity Modal */}
      {addModalAccountId && (
        <AddActivityModal
          isOpen={true}
          accountId={addModalAccountId}
          onClose={() => setAddModalAccountId(null)}
          onSaved={() => handleActivityChanged(addModalAccountId)}
        />
      )}
    </div>
  );
}
