import { useState } from "react";
import { accountsApi } from "@/api/accounts";
import { extractApiErrorMessage } from "@/utils/errors";
import { Modal } from "@/components/common/Modal";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function CreateManualAccountModal({ isOpen, onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [institutionName, setInstitutionName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      setError("Name is required");
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      await accountsApi.createManual({
        name: name.trim(),
        institution_name: institutionName.trim() || undefined,
      });
      onCreated();
      onClose();
      setName("");
      setInstitutionName("");
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to create account"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
        <h3 className="text-lg font-semibold mb-4">Add Manual Account</h3>

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Account Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              placeholder="e.g., Primary Residence"
              disabled={submitting}
              data-testid="manual-account-name"
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Institution (optional)
            </label>
            <input
              type="text"
              value={institutionName}
              onChange={(e) => setInstitutionName(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              placeholder="e.g., Local Bank"
              disabled={submitting}
              data-testid="manual-account-institution"
            />
          </div>

          {error && (
            <div className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm" data-testid="manual-account-error">
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
            >
              {submitting ? "Creating..." : "Create"}
            </button>
          </div>
        </form>
    </Modal>
  );
}
