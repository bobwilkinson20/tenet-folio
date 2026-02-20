import type { SyncLogEntry } from "../../types/sync_session";

interface SyncLogModalProps {
  isOpen: boolean;
  onClose: () => void;
  syncing: boolean;
  syncLog: SyncLogEntry[] | null;
  errorMessage: string | null;
}

function StatusBadge({ status }: { status: SyncLogEntry["status"] }) {
  const styles = {
    success: "bg-tf-positive/10 text-tf-positive",
    failed: "bg-tf-negative/10 text-tf-negative",
    partial: "bg-tf-warning/10 text-tf-warning",
  };

  return (
    <span
      className={`px-2 py-1 rounded-full text-xs font-semibold ${styles[status]}`}
    >
      {status}
    </span>
  );
}

export function SyncLogModal({
  isOpen,
  onClose,
  syncing,
  syncLog,
  errorMessage,
}: SyncLogModalProps) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      data-testid="sync-log-modal"
    >
      <div className="bg-tf-bg-surface border border-tf-border-default rounded-lg w-full max-w-lg mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-tf-border-subtle">
          <h2 className="text-lg font-semibold text-tf-text-primary">Sync Results</h2>
          <button
            onClick={onClose}
            className="text-tf-text-tertiary hover:text-tf-text-secondary"
            data-testid="sync-log-close"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4">
          {syncing ? (
            <div
              className="flex items-center justify-center py-8"
              data-testid="sync-log-loading"
            >
              <svg
                className="animate-spin h-6 w-6 text-tf-accent-primary mr-3"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span className="text-tf-text-secondary">Syncing portfolios...</span>
            </div>
          ) : errorMessage && !syncLog ? (
            <div
              className="bg-tf-negative/10 border border-tf-negative/20 rounded-md p-4"
              data-testid="sync-log-error"
            >
              <p className="text-sm text-tf-negative">{errorMessage}</p>
            </div>
          ) : syncLog && syncLog.length > 0 ? (
            <div className="space-y-3" data-testid="sync-log-results">
              {syncLog.map((entry) => (
                <div
                  key={entry.id}
                  className="border border-tf-border-default rounded-md p-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-tf-text-primary">
                      {entry.provider_name}
                    </span>
                    <StatusBadge status={entry.status} />
                  </div>
                  <p className="text-sm text-tf-text-tertiary mt-1">
                    {entry.accounts_synced} account
                    {entry.accounts_synced !== 1 ? "s" : ""} synced
                  </p>
                  {entry.error_messages && entry.error_messages.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {entry.error_messages.map((msg, i) => (
                        <div
                          key={i}
                          className="bg-tf-negative/10 border border-tf-negative/20 rounded p-2"
                        >
                          <p className="text-xs text-tf-negative">{msg}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-tf-text-tertiary text-center py-4">No sync data.</p>
          )}
        </div>

        {/* Footer */}
        {!syncing && (
          <div className="px-6 py-3 border-t border-tf-border-subtle flex justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-tf-bg-elevated text-tf-text-secondary rounded-md hover:text-tf-text-primary text-sm font-medium"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
