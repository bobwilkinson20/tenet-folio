import { useState, useEffect } from "react";
import { accountsApi } from "@/api/accounts";
import { assetTypeApi } from "@/api/assetTypes";
import { AssetTypeSelect } from "@/components/common/AssetTypeSelect";
import { AccountTypeSelect } from "@/components/common/AccountTypeSelect";
import type { Account, AccountType } from "@/types";
import type { AssetType } from "@/types/assetType";
import { extractApiErrorMessage } from "@/utils/errors";
import { Modal } from "@/components/common/Modal";

interface Props {
  isOpen: boolean;
  account: Account | null;
  onClose: () => void;
  onSaved: (id: string, updates: Partial<Account>) => void;
}

export function EditAccountDialog({ isOpen, account, onClose, onSaved }: Props) {
  const [name, setName] = useState("");
  const [accountType, setAccountType] = useState<AccountType | null>(null);
  const [assetClassId, setAssetClassId] = useState<string | null>(null);
  const [includeInAllocation, setIncludeInAllocation] = useState(true);
  const [assetTypes, setAssetTypes] = useState<AssetType[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (account) {
      setName(account.name);
      setAccountType(account.account_type ?? null);
      setAssetClassId(account.assigned_asset_class_id);
      setIncludeInAllocation(account.include_in_allocation);
      setError(null);
    }
  }, [account]);

  useEffect(() => {
    if (isOpen) {
      assetTypeApi.list().then((res) => setAssetTypes(res.data.items)).catch(() => {});
    }
  }, [isOpen]);

  if (!account) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Name is required");
      return;
    }

    // Build patch with only changed fields
    const updates: Record<string, unknown> = {};
    if (trimmedName !== account.name) updates.name = trimmedName;
    if (accountType !== (account.account_type ?? null)) {
      updates.account_type = accountType;
    }
    if (assetClassId !== account.assigned_asset_class_id) {
      updates.assigned_asset_class_id = assetClassId;
    }
    if (includeInAllocation !== account.include_in_allocation) {
      updates.include_in_allocation = includeInAllocation;
    }

    if (Object.keys(updates).length === 0) {
      onClose();
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      const response = await accountsApi.update(account.id, updates);
      onSaved(account.id, response.data);
      onClose();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to update account"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
        <h3 className="text-lg font-semibold mb-4">Edit Account</h3>

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              disabled={submitting}
              data-testid="edit-account-name"
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Account Type
            </label>
            <AccountTypeSelect
              value={accountType}
              onChange={setAccountType}
              disabled={submitting}
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Asset Type Override
            </label>
            <AssetTypeSelect
              value={assetClassId}
              onChange={setAssetClassId}
              assetTypes={assetTypes}
              disabled={submitting}
              placeholder="None (use individual security types)"
            />
          </div>

          <div className="mb-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={includeInAllocation}
                onChange={(e) => setIncludeInAllocation(e.target.checked)}
                className="h-4 w-4 rounded border-tf-border-default text-tf-accent-primary focus-visible:ring-tf-accent-primary"
                disabled={submitting}
                data-testid="edit-include-in-allocation"
              />
              <span className="text-sm text-tf-text-secondary">
                Include in portfolio target allocation
              </span>
            </label>
          </div>

          {error && (
            <div
              className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm"
              data-testid="edit-account-error"
            >
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-tf-text-secondary hover:bg-tf-bg-elevated rounded transition"
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-tf-accent-primary text-tf-text-primary rounded hover:bg-tf-accent-hover transition disabled:opacity-50"
              disabled={submitting}
              data-testid="edit-account-save"
            >
              {submitting ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
    </Modal>
  );
}
