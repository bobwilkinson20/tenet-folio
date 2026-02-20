import { useState } from "react";
import { useDashboard, usePreferences } from "../hooks";
import { syncApi } from "../api";
import type { SyncResponse } from "../api/sync";
import { SyncButton } from "../components/dashboard/SyncButton";
import { SyncLogModal } from "../components/dashboard/SyncLogModal";
import { AccountsTray } from "../components/dashboard/AccountsTray";
import { AllocationTable } from "../components/dashboard/AllocationTable";
import { AllocationChart } from "../components/dashboard/AllocationChart";
import { AllocationFilterToggle } from "../components/dashboard/AllocationFilterToggle";
import { NetWorthChart } from "../components/dashboard/NetWorthChart";
import { UnassignedAlert } from "../components/dashboard/UnassignedAlert";
import { ValuationWarning } from "../components/dashboard/ValuationWarning";
import { CostBasisCard } from "../components/dashboard/CostBasisCard";
import { ReturnsCard } from "../components/dashboard/ReturnsCard";
import { formatCurrency } from "@/utils/format";

/** Notion-style sidebar icon: rectangle with vertical divider on the left third. */
function SidebarIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="9" y1="3" x2="9" y2="21" />
    </svg>
  );
}

export function DashboardPage() {
  const { loading: prefsLoading, getPreference, setPreference } = usePreferences();
  const allocationOnly = getPreference("dashboard.allocationOnly", false);
  const trayOpen = getPreference("dashboard.accountsTrayOpen", false);
  const selectedAccountIds = getPreference<string[] | null>("dashboard.selectedAccountIds", null);
  const { dashboard, loading, refetch } = useDashboard(allocationOnly, !prefsLoading, selectedAccountIds);
  const accountIdsParam = selectedAccountIds?.join(",") || undefined;
  const [syncing, setSyncing] = useState(false);
  const [showSyncLog, setShowSyncLog] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResponse | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    setSyncError(null);
    setShowSyncLog(true);

    try {
      const response = await syncApi.trigger();
      setSyncResult(response.data);
      await refetch();
    } catch (err) {
      // Check for 409 Conflict (sync already in progress)
      const axiosErr = err as {
        response?: {
          status?: number;
          data?: SyncResponse | { detail?: string };
        }
      };

      if (axiosErr.response?.status === 409) {
        // Sync already in progress - show friendly message
        setSyncError("Sync is already in progress. Please wait for it to complete.");
        setShowSyncLog(false); // Don't show sync log for 409
      } else if (axiosErr.response?.data && 'sync_log' in axiosErr.response.data) {
        // Sync was attempted but failed - show sync log
        setSyncResult(axiosErr.response.data as SyncResponse);
      } else {
        // Other errors
        const responseData = axiosErr.response?.data;
        const errorMsg = (responseData && 'detail' in responseData)
          ? responseData.detail || "Sync failed"
          : (err instanceof Error ? err.message : "Sync failed");
        setSyncError(errorMsg);
      }
    } finally {
      setSyncing(false);
    }
  };

  if (prefsLoading || (loading && !dashboard)) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-tf-text-tertiary">Loading dashboard...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() =>
              setPreference("dashboard.accountsTrayOpen", !trayOpen)
            }
            className="p-1.5 rounded-md text-tf-text-tertiary hover:text-tf-text-primary hover:bg-tf-bg-elevated transition-colors"
            data-testid="accounts-tray-toggle"
            aria-label={trayOpen ? "Hide accounts sidebar" : "Show accounts sidebar"}
            title={trayOpen ? "Hide accounts sidebar" : "Show accounts sidebar"}
          >
            <SidebarIcon className="w-5 h-5" />
          </button>
          <SyncButton onSync={handleSync} syncing={syncing} />
        </div>
        <AllocationFilterToggle
          enabled={allocationOnly}
          onChange={(value) =>
            setPreference("dashboard.allocationOnly", value)
          }
        />
      </div>

      {/* Sidebar + Content */}
      <div className="flex gap-6 min-h-[calc(100vh-12rem)]">
        {/* Accounts Sidebar */}
        <AccountsTray
          accounts={dashboard?.accounts ?? []}
          isOpen={trayOpen}
          selectedAccountIds={selectedAccountIds}
          onSelectionChange={(ids) =>
            setPreference("dashboard.selectedAccountIds", ids)
          }
        />

        {/* Main dashboard content */}
        <div className="flex-1 min-w-0 space-y-6">
          {/* Valuation Warning Banner */}
          {dashboard && <ValuationWarning accounts={dashboard.accounts} />}

          {/* Net Worth Card */}
          <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl p-6">
            <p className="text-tf-text-secondary text-sm font-medium">Total Net Worth</p>
            <p className="text-4xl font-bold mt-1">
              {dashboard ? formatCurrency(dashboard.total_net_worth) : "$0.00"}
            </p>
          </div>

          {/* Sync Log Modal */}
          <SyncLogModal
            isOpen={showSyncLog}
            onClose={() => setShowSyncLog(false)}
            syncing={syncing}
            syncLog={syncResult?.sync_log ?? null}
            errorMessage={syncError}
          />

          {/* Cost Basis Card */}
          <CostBasisCard accountIds={accountIdsParam} />

          {/* Returns Card */}
          <ReturnsCard accountIds={accountIdsParam} />

          {/* Net Worth Chart */}
          <NetWorthChart allocationOnly={allocationOnly} accountIds={accountIdsParam} />

          {/* Unassigned Securities Alert */}
          {dashboard && dashboard.unassigned_count > 0 && (
            <UnassignedAlert
              count={dashboard.unassigned_count}
              value={dashboard.unassigned_value}
            />
          )}

          {/* Allocation Visualization */}
          {dashboard &&
            dashboard.allocations &&
            dashboard.allocations.length > 0 && (
              <div className="grid gap-6 lg:grid-cols-2">
                <AllocationTable
                  allocations={dashboard.allocations}
                  unassignedValue={dashboard.unassigned_value || "0"}
                  allocationTotal={dashboard.allocation_total}
                />
                <AllocationChart
                  allocations={dashboard.allocations}
                  totalValue={dashboard.allocation_total}
                />
              </div>
            )}
        </div>
      </div>
    </div>
  );
}
