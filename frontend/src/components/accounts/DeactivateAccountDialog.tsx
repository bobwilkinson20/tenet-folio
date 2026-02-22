import { useState } from "react";
import { accountsApi } from "@/api/accounts";
import type { Account } from "@/types";
import { extractApiErrorMessage } from "@/utils/errors";
import { Modal } from "@/components/common/Modal";

interface Props {
  isOpen: boolean;
  account: Account | null;
  allAccounts: Account[];
  onClose: () => void;
  onDeactivated: (updated: Account) => void;
}

export function DeactivateAccountDialog({
  isOpen,
  account,
  allAccounts,
  onClose,
  onDeactivated,
}: Props) {
  const [createClosingSnapshot, setCreateClosingSnapshot] = useState(true);
  const [supersededById, setSupersededById] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!account) return null;

  const hasValue = account.value && parseFloat(account.value) > 0;

  // Candidate replacement accounts: active and not this account
  const replacementCandidates = allAccounts.filter(
    (a) => a.is_active && a.id !== account.id
  );

  const handleConfirm = async () => {
    try {
      setSubmitting(true);
      setError(null);
      const response = await accountsApi.deactivate(account.id, {
        create_closing_snapshot: hasValue ? createClosingSnapshot : false,
        superseded_by_account_id: supersededById || null,
      });
      onDeactivated(response.data);
      onClose();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to deactivate account"));
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!submitting) {
      setCreateClosingSnapshot(true);
      setSupersededById("");
      setError(null);
      onClose();
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose}>
      <h3 className="text-lg font-semibold mb-2">Deactivate Account</h3>

      <div className="mb-4 space-y-2">
        <p className="text-sm text-tf-text-secondary">
          Deactivating{" "}
          <span className="font-medium">{account.name}</span> will stop syncing
          it and exclude it from current allocation. Historical data is
          preserved.
        </p>
        {account.institution_name && (
          <p className="text-xs text-tf-text-tertiary">
            {account.institution_name} &middot; {account.provider_name}
          </p>
        )}
      </div>

      {hasValue && (
        <div className="mb-4 p-3 bg-tf-bg-elevated rounded border border-tf-border-default space-y-3">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={createClosingSnapshot}
              onChange={(e) => setCreateClosingSnapshot(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-tf-border-default text-tf-accent-primary focus-visible:ring-tf-accent-primary"
              data-testid="closing-snapshot-checkbox"
            />
            <div>
              <span className="text-sm font-medium text-tf-text-primary">
                Record a closing snapshot (recommended)
              </span>
              <p className="text-xs text-tf-text-tertiary mt-0.5">
                Writes a $0 balance for today so portfolio history shows a
                clean end date rather than an abrupt gap.
              </p>
            </div>
          </label>
        </div>
      )}

      {replacementCandidates.length > 0 && (
        <div className="mb-4">
          <label className="block text-sm font-medium text-tf-text-secondary mb-1">
            Replaced by (optional)
          </label>
          <select
            value={supersededById}
            onChange={(e) => setSupersededById(e.target.value)}
            className="w-full rounded border border-tf-border-default bg-tf-bg-surface text-tf-text-primary text-sm px-3 py-2 focus:outline-none focus:ring-1 focus:ring-tf-accent-primary"
            data-testid="superseded-by-select"
          >
            <option value="">None</option>
            {replacementCandidates.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
                {a.institution_name ? ` — ${a.institution_name}` : ""}
                {` (${a.provider_name})`}
              </option>
            ))}
          </select>
          <p className="text-xs text-tf-text-tertiary mt-1">
            Links this account to its replacement for reference. Shown as a
            badge on the deactivated account.
          </p>
        </div>
      )}

      {error && (
        <div
          className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm"
          data-testid="deactivate-account-error"
        >
          {error}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={handleClose}
          className="px-4 py-2 text-tf-text-secondary hover:bg-tf-bg-elevated rounded transition"
          disabled={submitting}
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleConfirm}
          className="px-4 py-2 bg-tf-warning text-tf-text-primary rounded hover:opacity-90 transition disabled:opacity-50"
          disabled={submitting}
          data-testid="confirm-deactivate-account"
        >
          {submitting ? "Deactivating..." : "Deactivate Account"}
        </button>
      </div>
    </Modal>
  );
}
