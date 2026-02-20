import { useState } from "react";
import { accountsApi } from "@/api/accounts";
import type { Account } from "@/types";
import { extractApiErrorMessage } from "@/utils/errors";
import { Modal } from "@/components/common/Modal";

interface Props {
  isOpen: boolean;
  account: Account | null;
  onClose: () => void;
  onDeleted: (id: string) => void;
}

export function DeleteAccountDialog({
  isOpen,
  account,
  onClose,
  onDeleted,
}: Props) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!account) return null;

  const handleConfirm = async () => {
    try {
      setDeleting(true);
      setError(null);
      await accountsApi.delete(account.id);
      onDeleted(account.id);
      onClose();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to delete account"));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
        <h3 className="text-lg font-semibold mb-2">Delete Account</h3>

        {account.provider_name === "Manual" ? (
          <div className="mb-4 space-y-2">
            <p className="text-sm text-tf-text-secondary">
              Are you sure you want to delete{" "}
              <span className="font-medium">{account.name}</span>?
            </p>
            <p className="text-sm text-tf-negative font-medium">
              This is permanent. All holdings, history, and data for this manual
              account will be lost and cannot be recovered.
            </p>
          </div>
        ) : (
          <div className="mb-4 space-y-2">
            <p className="text-sm text-tf-text-secondary">
              Are you sure you want to delete{" "}
              <span className="font-medium">{account.name}</span>?
            </p>
            <p className="text-sm text-tf-text-secondary">
              This will remove the account and its local data. Note that this
              account will be recreated on the next sync from{" "}
              <span className="font-medium">{account.provider_name}</span>.
            </p>
          </div>
        )}

        {error && (
          <div
            className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm"
            data-testid="delete-account-error"
          >
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-tf-text-secondary hover:bg-tf-bg-elevated rounded transition"
            disabled={deleting}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="px-4 py-2 bg-tf-negative text-tf-text-primary rounded hover:opacity-90 transition disabled:opacity-50"
            disabled={deleting}
            data-testid="confirm-delete-account"
          >
            {deleting ? "Deleting..." : "Delete"}
          </button>
        </div>
    </Modal>
  );
}
