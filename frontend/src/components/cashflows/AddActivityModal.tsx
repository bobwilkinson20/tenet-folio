import { useState } from "react";
import { accountsApi } from "@/api/accounts";
import { extractApiErrorMessage } from "@/utils/errors";
import { Modal } from "@/components/common/Modal";

const ACTIVITY_TYPES = [
  "deposit",
  "withdrawal",
  "transfer_in",
  "transfer_out",
  "buy",
  "sell",
  "dividend",
  "interest",
  "fee",
  "tax",
  "other",
];

interface Props {
  isOpen: boolean;
  accountId: string;
  onClose: () => void;
  onSaved: () => void;
}

export function AddActivityModal({ isOpen, accountId, onClose, onSaved }: Props) {
  const [activityDate, setActivityDate] = useState("");
  const [type, setType] = useState("deposit");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [ticker, setTicker] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!activityDate) {
      setError("Date is required");
      return;
    }
    if (!type) {
      setError("Type is required");
      return;
    }

    if (amount) {
      const parsed = parseFloat(amount);
      if (isNaN(parsed)) {
        setError("Amount must be a valid number");
        return;
      }
    }

    try {
      setSubmitting(true);
      setError(null);
      const trimmedNotes = notes.trim();
      await accountsApi.createActivity(accountId, {
        activity_date: `${activityDate}T00:00:00`,
        type,
        amount: amount ? parseFloat(amount) : undefined,
        description: description.trim() || undefined,
        ticker: ticker.trim() || undefined,
        notes: trimmedNotes || undefined,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to create activity"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <h3 className="text-lg font-semibold mb-4">Add Activity</h3>

      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Date
            </label>
            <input
              type="date"
              value={activityDate}
              onChange={(e) => setActivityDate(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              disabled={submitting}
              data-testid="add-date"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Type
            </label>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              disabled={submitting}
              data-testid="add-type"
            >
              {ACTIVITY_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Amount
            </label>
            <input
              type="number"
              step="any"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              placeholder="0.00"
              disabled={submitting}
              data-testid="add-amount"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Ticker
            </label>
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              placeholder="Optional"
              disabled={submitting}
              data-testid="add-ticker"
            />
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-tf-text-secondary mb-2">
            Description
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
            placeholder="Optional"
            disabled={submitting}
            data-testid="add-description"
          />
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-tf-text-secondary mb-2">
            Notes
          </label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
            placeholder="Optional"
            disabled={submitting}
            data-testid="add-notes"
          />
        </div>

        {error && (
          <div className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm" data-testid="add-error">
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
            data-testid="add-submit"
          >
            {submitting ? "Creating..." : "Create"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
