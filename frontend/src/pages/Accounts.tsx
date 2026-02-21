import { useState } from "react";
import { useAccounts, usePreferences } from "../hooks";
import { AccountList } from "../components/accounts/AccountList";
import { CreateManualAccountModal } from "../components/accounts/CreateManualAccountModal";
import { EditAccountDialog } from "../components/accounts/EditAccountDialog";
import { DeleteAccountDialog } from "../components/accounts/DeleteAccountDialog";
import { DeactivateAccountDialog } from "../components/accounts/DeactivateAccountDialog";
import { SyncButton } from "../components/dashboard/SyncButton";
import { SyncLogModal } from "../components/dashboard/SyncLogModal";
import { syncApi } from "../api";
import type { SyncResponse } from "../api/sync";
import { accountsApi } from "../api";
import type { Account } from "../types";

export function AccountsPage() {
  const { accounts, loading, refetch, updateAccount, deleteAccount } = useAccounts();
  const { getPreference, setPreference } = usePreferences();
  const hideInactive = getPreference("accounts.hideInactive", false);
  const [syncing, setSyncing] = useState(false);
  const [showSyncLog, setShowSyncLog] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResponse | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [showCreateManual, setShowCreateManual] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [deletingAccount, setDeletingAccount] = useState<Account | null>(null);
  const [deactivatingAccount, setDeactivatingAccount] = useState<Account | null>(null);

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

  const handleEdit = (account: Account) => {
    setEditingAccount(account);
  };

  const handleToggleActive = (account: Account) => {
    if (account.is_active) {
      // Deactivating: open the dialog to allow closing snapshot + replacement link
      setDeactivatingAccount(account);
    } else {
      // Re-activating: simple optimistic toggle, no dialog needed
      updateAccount(account.id, { is_active: true });
      accountsApi.update(account.id, { is_active: true }).catch((error) => {
        updateAccount(account.id, { is_active: false });
        console.error("Failed to reactivate account:", error);
      });
    }
  };

  const handleDeactivated = (updated: Account) => {
    updateAccount(updated.id, updated);
  };

  const handleDelete = (account: Account) => {
    setDeletingAccount(account);
  };

  const handleEditSaved = (id: string, updates: Partial<Account>) => {
    updateAccount(id, updates);
  };

  const handleDeleteConfirmed = (id: string) => {
    deleteAccount(id);
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold text-tf-text-primary mb-2">Accounts</h2>
        <p className="text-tf-text-secondary">
          Manage your connected brokerage accounts
        </p>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <SyncButton onSync={handleSync} syncing={syncing} />
          <button
            onClick={() => setShowCreateManual(true)}
            className="px-4 py-2 bg-tf-accent-primary text-tf-text-primary rounded hover:bg-tf-accent-hover transition text-sm font-medium"
            data-testid="add-manual-account-button"
          >
            Add Manual Account
          </button>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={hideInactive}
            onChange={(e) => setPreference("accounts.hideInactive", e.target.checked)}
            className="h-4 w-4 rounded border-tf-border-default text-tf-accent-primary focus-visible:ring-tf-accent-primary"
            data-testid="hide-inactive-toggle"
          />
          <span className="text-sm text-tf-text-secondary">Hide inactive accounts</span>
        </label>
      </div>

      <CreateManualAccountModal
        isOpen={showCreateManual}
        onClose={() => setShowCreateManual(false)}
        onCreated={refetch}
      />

      <EditAccountDialog
        isOpen={!!editingAccount}
        account={editingAccount}
        onClose={() => setEditingAccount(null)}
        onSaved={handleEditSaved}
      />

      <DeleteAccountDialog
        isOpen={!!deletingAccount}
        account={deletingAccount}
        onClose={() => setDeletingAccount(null)}
        onDeleted={handleDeleteConfirmed}
      />

      <DeactivateAccountDialog
        isOpen={!!deactivatingAccount}
        account={deactivatingAccount}
        allAccounts={accounts}
        onClose={() => setDeactivatingAccount(null)}
        onDeactivated={handleDeactivated}
      />

      <SyncLogModal
        isOpen={showSyncLog}
        onClose={() => setShowSyncLog(false)}
        syncing={syncing}
        syncLog={syncResult?.sync_log ?? null}
        errorMessage={syncError}
      />

      <div className="mt-8">
        <AccountList
          accounts={accounts}
          loading={loading}
          onEdit={handleEdit}
          onToggleActive={handleToggleActive}
          onDelete={handleDelete}
          hideInactive={hideInactive}
        />
      </div>
    </div>
  );
}
