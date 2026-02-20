import { useEffect, useState } from "react";
import { accountsApi } from "@/api/accounts";
import { extractApiErrorMessage } from "@/utils/errors";
import { Modal } from "@/components/common/Modal";
import type { HoldingLot } from "@/types";

interface Props {
  isOpen: boolean;
  lot: HoldingLot | null; // null = create, populated = edit
  accountId: string;
  securityId: string;
  ticker: string;
  holdingQuantity?: number;
  otherLots: HoldingLot[];
  onClose: () => void;
  onSaved: () => void;
}

export function LotFormModal({
  isOpen,
  lot,
  accountId,
  securityId,
  ticker,
  holdingQuantity,
  otherLots,
  onClose,
  onSaved,
}: Props) {
  const [acquisitionDate, setAcquisitionDate] = useState("");
  const [costBasisPerUnit, setCostBasisPerUnit] = useState("");
  const [quantity, setQuantity] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Remainder lot fields
  const [remainderDate, setRemainderDate] = useState("");
  const [remainderCostBasis, setRemainderCostBasis] = useState("");

  const isEdit = lot !== null;

  const otherLotsTotal = otherLots.reduce(
    (sum, l) => sum + Number(l.current_quantity),
    0,
  );

  const qty = parseFloat(quantity);
  const validQty = !isNaN(qty) && qty > 0;
  const remainder =
    holdingQuantity != null && validQty
      ? holdingQuantity - otherLotsTotal - qty
      : null;
  const hasRemainder = remainder != null && remainder > 0;
  const exceedsHolding = remainder != null && remainder < 0;

  useEffect(() => {
    if (lot) {
      setAcquisitionDate(lot.acquisition_date ?? "");
      setCostBasisPerUnit(String(lot.cost_basis_per_unit));
      setQuantity(String(lot.original_quantity));
    } else {
      setAcquisitionDate("");
      setCostBasisPerUnit("");
      setQuantity("");
    }
    setRemainderDate("");
    setRemainderCostBasis("");
    setError(null);
  }, [lot, isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!acquisitionDate) {
      setError("Acquisition date is required");
      return;
    }

    const cbpu = parseFloat(costBasisPerUnit);
    if (isNaN(cbpu) || cbpu < 0) {
      setError("A valid cost basis per unit is required");
      return;
    }

    const qtyVal = parseFloat(quantity);
    if (isNaN(qtyVal) || qtyVal <= 0) {
      setError("A valid quantity is required");
      return;
    }

    if (exceedsHolding) {
      setError("Lot total would exceed holding quantity");
      return;
    }

    // Validate remainder fields if remainder row is showing
    if (hasRemainder) {
      if (!remainderDate) {
        setError("Acquisition date is required for the remainder lot");
        return;
      }
      const remCbpu = parseFloat(remainderCostBasis);
      if (isNaN(remCbpu) || remCbpu < 0) {
        setError("A valid cost basis per unit is required for the remainder lot");
        return;
      }
    }

    try {
      setSubmitting(true);
      setError(null);

      if (hasRemainder) {
        // Use batch API
        const remCbpu = parseFloat(remainderCostBasis);
        await accountsApi.saveLotsBatch(accountId, securityId, {
          updates: isEdit
            ? [
                {
                  id: lot.id,
                  acquisition_date: acquisitionDate,
                  cost_basis_per_unit: cbpu,
                  quantity: qtyVal,
                },
              ]
            : [],
          creates: [
            ...(isEdit
              ? []
              : [
                  {
                    ticker,
                    acquisition_date: acquisitionDate,
                    cost_basis_per_unit: cbpu,
                    quantity: qtyVal,
                  },
                ]),
            {
              ticker,
              acquisition_date: remainderDate,
              cost_basis_per_unit: remCbpu,
              quantity: remainder,
            },
          ],
        });
      } else if (isEdit) {
        await accountsApi.updateLot(accountId, lot.id, {
          acquisition_date: acquisitionDate,
          cost_basis_per_unit: cbpu,
          quantity: qtyVal,
        });
      } else {
        await accountsApi.createLot(accountId, {
          ticker,
          acquisition_date: acquisitionDate,
          cost_basis_per_unit: cbpu,
          quantity: qtyVal,
        });
      }

      onSaved();
      onClose();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to save lot"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <h3 className="text-lg font-semibold mb-4">
        {isEdit ? "Edit Lot" : "Add Lot"} — {ticker}
      </h3>

      <form onSubmit={handleSubmit}>
        <div className="mb-4">
          <label className="block text-sm font-medium text-tf-text-secondary mb-2">
            Acquisition Date
          </label>
          <input
            type="date"
            value={acquisitionDate}
            onChange={(e) => setAcquisitionDate(e.target.value)}
            className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
            disabled={submitting}
            data-testid="lot-acquisition-date"
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Cost Basis / Unit
            </label>
            <input
              type="number"
              step="any"
              value={costBasisPerUnit}
              onChange={(e) => setCostBasisPerUnit(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              placeholder="0.00"
              disabled={submitting}
              data-testid="lot-cost-basis"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Quantity
            </label>
            <input
              type="number"
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              placeholder="0"
              disabled={submitting}
              data-testid="lot-quantity"
            />
          </div>
        </div>

        {exceedsHolding && (
          <div
            className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm"
            data-testid="lot-exceeds-error"
          >
            Lot total would exceed holding quantity ({holdingQuantity})
          </div>
        )}

        {hasRemainder && (
          <div
            className="mb-4 p-4 bg-tf-bg-surface border border-tf-border-default rounded"
            data-testid="remainder-row"
          >
            <h4 className="text-sm font-semibold text-tf-text-secondary mb-3">
              Remainder Lot — {remainder.toLocaleString()} shares
            </h4>
            <div className="mb-3">
              <label className="block text-sm font-medium text-tf-text-secondary mb-1">
                Acquisition Date
              </label>
              <input
                type="date"
                value={remainderDate}
                onChange={(e) => setRemainderDate(e.target.value)}
                className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
                disabled={submitting}
                data-testid="remainder-acquisition-date"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-tf-text-secondary mb-1">
                  Cost Basis / Unit
                </label>
                <input
                  type="number"
                  step="any"
                  value={remainderCostBasis}
                  onChange={(e) => setRemainderCostBasis(e.target.value)}
                  className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
                  placeholder="0.00"
                  disabled={submitting}
                  data-testid="remainder-cost-basis"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-tf-text-secondary mb-1">
                  Quantity
                </label>
                <input
                  type="number"
                  value={remainder}
                  className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-tertiary"
                  disabled
                  data-testid="remainder-quantity"
                />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm" data-testid="lot-form-error">
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
            disabled={submitting || exceedsHolding}
          >
            {submitting ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
