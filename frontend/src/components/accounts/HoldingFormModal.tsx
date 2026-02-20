import { useEffect, useState } from "react";
import { accountsApi } from "@/api/accounts";
import { isSyntheticTicker } from "@/utils/ticker";
import type { Holding } from "@/types/sync_session";
import { extractApiErrorMessage } from "@/utils/errors";
import { Modal } from "@/components/common/Modal";

type AssetType = "security" | "other";

interface Props {
  isOpen: boolean;
  holding: Holding | null; // null = create, populated = edit
  accountId: string;
  existingTickers?: string[];
  onClose: () => void;
  onSaved: () => void;
}

export function HoldingFormModal({
  isOpen,
  holding,
  accountId,
  existingTickers = [],
  onClose,
  onSaved,
}: Props) {
  const [assetType, setAssetType] = useState<AssetType>("security");
  const [ticker, setTicker] = useState("");
  const [description, setDescription] = useState("");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [marketValue, setMarketValue] = useState("");
  const [acquisitionDate, setAcquisitionDate] = useState("");
  const [costBasisPerUnit, setCostBasisPerUnit] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEdit = holding !== null;

  useEffect(() => {
    if (holding) {
      if (isSyntheticTicker(holding.ticker)) {
        setAssetType("other");
        setDescription(holding.security_name || "");
        setTicker("");
        setQuantity("");
        setPrice("");
      } else {
        setAssetType("security");
        setTicker(holding.ticker);
        setDescription("");
        setQuantity(String(holding.quantity));
        setPrice(String(holding.snapshot_price));
      }
      setMarketValue(String(holding.snapshot_value));
    } else {
      setAssetType("security");
      setTicker("");
      setDescription("");
      setQuantity("");
      setPrice("");
      setMarketValue("");
    }
    setAcquisitionDate("");
    setCostBasisPerUnit("");
    setError(null);
  }, [holding, isOpen]);

  // Auto-calculate market_value when both quantity and price are entered (security mode only)
  useEffect(() => {
    if (assetType !== "security") return;
    const q = parseFloat(quantity);
    const p = parseFloat(price);
    if (!isNaN(q) && !isNaN(p) && q > 0 && p > 0) {
      setMarketValue(String(q * p));
    }
  }, [quantity, price, assetType]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (assetType === "security") {
      if (!ticker.trim()) {
        setError("Ticker is required");
        return;
      }
      const q = parseFloat(quantity);
      if (isNaN(q) || q <= 0) {
        setError("Quantity is required and must be greater than zero");
        return;
      }
    } else {
      if (!description.trim()) {
        setError("Description is required");
        return;
      }
    }

    const mv = parseFloat(marketValue);
    if (isNaN(mv)) {
      setError("A valid market value is required");
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      if (assetType === "security") {
        const data: Record<string, string | number> = {
          ticker: ticker.trim().toUpperCase(),
          market_value: mv,
        };

        const q = parseFloat(quantity);
        const p = parseFloat(price);
        if (!isNaN(q)) data.quantity = q;
        if (!isNaN(p)) data.price = p;

        if (!isEdit) {
          if (acquisitionDate) data.acquisition_date = acquisitionDate;
          const cb = parseFloat(costBasisPerUnit);
          if (!isNaN(cb)) data.cost_basis_per_unit = cb;
          await accountsApi.addHolding(accountId, data);
        } else {
          await accountsApi.updateHolding(accountId, holding.id, data);
        }
      } else {
        const data: Record<string, string | number> = {
          description: description.trim(),
          market_value: mv,
        };

        if (!isEdit) {
          if (acquisitionDate) data.acquisition_date = acquisitionDate;
          const cb = parseFloat(costBasisPerUnit);
          if (!isNaN(cb)) data.cost_basis_per_unit = cb;
          await accountsApi.addHolding(accountId, data);
        } else {
          await accountsApi.updateHolding(accountId, holding.id, data);
        }
      }

      onSaved();
      onClose();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to save holding"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
        <h3 className="text-lg font-semibold mb-4">
          {isEdit ? "Edit Holding" : "Add Holding"}
        </h3>

        <form onSubmit={handleSubmit}>
          {/* Asset Type Picker */}
          <div className="mb-4" data-testid="asset-type-picker">
          {isEdit && (
            <p className="mb-1 text-xs text-tf-text-tertiary">
              Asset type cannot be changed. Delete and recreate to switch.
            </p>
          )}
          <div className="flex rounded-lg overflow-hidden border border-tf-border-default">
            <button
              type="button"
              onClick={() => !isEdit && setAssetType("security")}
              className={`flex-1 px-4 py-2 text-sm font-medium transition ${
                assetType === "security"
                  ? "bg-tf-accent-primary text-tf-text-primary"
                  : "bg-tf-bg-surface text-tf-text-secondary hover:bg-tf-bg-elevated"
              } ${isEdit ? "cursor-not-allowed opacity-75" : ""}`}
              disabled={isEdit}
              data-testid="asset-type-security"
            >
              Security
            </button>
            <button
              type="button"
              onClick={() => !isEdit && setAssetType("other")}
              className={`flex-1 px-4 py-2 text-sm font-medium transition ${
                assetType === "other"
                  ? "bg-tf-accent-primary text-tf-text-primary"
                  : "bg-tf-bg-surface text-tf-text-secondary hover:bg-tf-bg-elevated"
              } ${isEdit ? "cursor-not-allowed opacity-75" : ""}`}
              disabled={isEdit}
              data-testid="asset-type-other"
            >
              Other
            </button>
          </div>
          </div>

          {assetType === "security" ? (
            <>
              <div className="mb-4">
                <label className="block text-sm font-medium text-tf-text-secondary mb-2">
                  Ticker
                </label>
                <input
                  type="text"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value)}
                  className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
                  placeholder="e.g., HOME, AAPL"
                  disabled={submitting}
                  data-testid="holding-ticker"
                />
                {!isEdit && ticker.trim() !== "" && existingTickers.includes(ticker.trim().toUpperCase()) && (
                  <p className="mt-1 text-xs text-tf-warning" data-testid="duplicate-ticker-warning">
                    A holding for {ticker.trim().toUpperCase()} already exists. You can edit it instead.
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4 mb-4">
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
                    data-testid="holding-quantity"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-tf-text-secondary mb-2">
                    Price (optional)
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                    className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
                    placeholder="0.00"
                    disabled={submitting}
                    data-testid="holding-price"
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="mb-4">
              <label className="block text-sm font-medium text-tf-text-secondary mb-2">
                Description
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
                placeholder="e.g., Primary Residence, Art Collection"
                disabled={submitting}
                data-testid="holding-description"
              />
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              {assetType === "security" ? "Market Value" : "Value"}
            </label>
            <input
              type="number"
              step="any"
              value={marketValue}
              onChange={(e) => setMarketValue(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              placeholder="0.00"
              disabled={submitting}
              data-testid="holding-market-value"
            />
            {assetType === "security" && (
              <p className="mt-1 text-xs text-tf-text-tertiary">
                Auto-calculated from quantity and price, or enter directly
              </p>
            )}
          </div>

          {!isEdit && (
            <div className="mb-4">
              <p className="text-xs text-tf-text-tertiary mb-2">
                Leave blank to default to current value
              </p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-tf-text-secondary mb-2">
                    Acquisition Date
                  </label>
                  <input
                    type="date"
                    value={acquisitionDate}
                    onChange={(e) => setAcquisitionDate(e.target.value)}
                    className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
                    disabled={submitting}
                    data-testid="holding-acquisition-date"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-tf-text-secondary mb-2">
                    {assetType === "security" ? "Cost Basis / Unit" : "Total Cost Basis"}
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={costBasisPerUnit}
                    onChange={(e) => setCostBasisPerUnit(e.target.value)}
                    className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
                    placeholder="0.00"
                    disabled={submitting}
                    data-testid="holding-cost-basis"
                  />
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm" data-testid="holding-form-error">
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
              {submitting ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
    </Modal>
  );
}
