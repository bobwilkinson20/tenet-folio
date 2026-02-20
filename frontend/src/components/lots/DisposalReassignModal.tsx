import { useEffect, useState } from "react";
import { accountsApi } from "@/api/accounts";
import { extractApiErrorMessage } from "@/utils/errors";
import { Modal } from "@/components/common/Modal";
import type { HoldingLot, DisposalAssignment } from "@/types";

interface Props {
  isOpen: boolean;
  accountId: string;
  securityId: string;
  disposalGroupId: string;
  totalQuantity: number;
  disposalDate: string;
  proceedsPerUnit: number;
  onClose: () => void;
  onSaved: () => void;
}

export function DisposalReassignModal({
  isOpen,
  accountId,
  securityId,
  disposalGroupId,
  totalQuantity,
  disposalDate,
  proceedsPerUnit,
  onClose,
  onSaved,
}: Props) {
  const [lots, setLots] = useState<HoldingLot[]>([]);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    const fetchLots = async () => {
      try {
        setLoading(true);
        const resp = await accountsApi.getLotsBySecurity(accountId, securityId);
        // Show lots that have available quantity (open lots)
        setLots(resp.data.filter((l) => !l.is_closed));
        setAssignments({});
        setError(null);
      } catch {
        setLots([]);
      } finally {
        setLoading(false);
      }
    };
    fetchLots();
  }, [isOpen, accountId, securityId]);

  const assignedTotal = Object.values(assignments).reduce(
    (sum, val) => sum + (parseFloat(val) || 0),
    0,
  );
  const remaining = totalQuantity - assignedTotal;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (Math.abs(remaining) > 0.0001) {
      setError(`Total assigned quantity must equal ${totalQuantity}. Remaining: ${remaining.toFixed(4)}`);
      return;
    }

    const assignmentList: DisposalAssignment[] = Object.entries(assignments)
      .filter(([, val]) => parseFloat(val) > 0)
      .map(([lotId, val]) => ({
        lot_id: lotId,
        quantity: parseFloat(val),
      }));

    if (assignmentList.length === 0) {
      setError("At least one lot assignment is required");
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      await accountsApi.reassignDisposals(accountId, disposalGroupId, {
        assignments: assignmentList,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to reassign disposals"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} maxWidth="lg">
      <h3 className="text-lg font-semibold mb-2">Reassign Disposal</h3>
      <p className="text-sm text-tf-text-tertiary mb-4">
        Sell of {totalQuantity} shares on {disposalDate} at ${Number(proceedsPerUnit).toFixed(2)}/share
      </p>

      {loading ? (
        <p className="text-sm text-tf-text-tertiary">Loading lots...</p>
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <table className="w-full text-sm" data-testid="reassign-lots-table">
              <thead>
                <tr className="text-xs text-tf-text-tertiary uppercase">
                  <th className="text-left py-1 pr-3">Lot Date</th>
                  <th className="text-right py-1 px-3">Available</th>
                  <th className="text-right py-1 px-3">Cost/Unit</th>
                  <th className="text-right py-1 pl-3">Assign Qty</th>
                </tr>
              </thead>
              <tbody>
                {lots.map((lot) => (
                  <tr key={lot.id} className="border-t border-tf-border-subtle">
                    <td className="py-2 pr-3 text-tf-text-primary">{lot.acquisition_date ?? "Unknown"}</td>
                    <td className="py-2 px-3 text-right text-tf-text-tertiary">
                      {Number(lot.current_quantity).toLocaleString()}
                    </td>
                    <td className="py-2 px-3 text-right text-tf-text-tertiary">
                      ${Number(lot.cost_basis_per_unit).toFixed(2)}
                    </td>
                    <td className="py-2 pl-3 text-right">
                      <input
                        type="number"
                        step="any"
                        min="0"
                        max={lot.current_quantity}
                        value={assignments[lot.id] || ""}
                        onChange={(e) =>
                          setAssignments((prev) => ({
                            ...prev,
                            [lot.id]: e.target.value,
                          }))
                        }
                        className="w-24 px-2 py-1 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary text-right text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
                        disabled={submitting}
                        data-testid={`reassign-qty-${lot.id}`}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {lots.length === 0 && (
              <p className="text-sm text-tf-text-tertiary mt-2">No open lots available for reassignment.</p>
            )}
          </div>

          <div className="mb-4 flex justify-between text-sm">
            <span className="text-tf-text-tertiary">Total to assign: {totalQuantity}</span>
            <span className={Math.abs(remaining) < 0.0001 ? "text-tf-positive" : "text-tf-warning"}>
              Remaining: {remaining.toFixed(4)}
            </span>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm" data-testid="reassign-error">
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
              disabled={submitting || lots.length === 0}
            >
              {submitting ? "Reassigning..." : "Reassign"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
