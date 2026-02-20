import { useCallback, useEffect, useState } from "react";
import { accountsApi } from "@/api/accounts";
import { extractApiErrorMessage } from "@/utils/errors";
import { LotFormModal } from "./LotFormModal";
import { formatCurrency } from "@/utils/format";
import type { HoldingLot } from "@/types";

const SOURCE_LABELS: Record<string, string> = {
  activity: "Activity",
  inferred: "Inferred",
  initial: "Initial",
  manual: "Manual",
};

const SOURCE_COLORS: Record<string, string> = {
  activity: "bg-blue-500/20 text-blue-400",
  inferred: "bg-yellow-500/20 text-yellow-400",
  initial: "bg-purple-500/20 text-purple-400",
  manual: "bg-green-500/20 text-green-400",
};

interface Props {
  accountId: string;
  securityId: string;
  ticker: string;
  marketPrice?: number | null;
  holdingQuantity?: number;
}

export function LotDetailPanel({ accountId, securityId, ticker, marketPrice, holdingQuantity }: Props) {
  const [lots, setLots] = useState<HoldingLot[]>([]);
  const [loading, setLoading] = useState(true);
  const [showClosed, setShowClosed] = useState(false);
  const [showLotForm, setShowLotForm] = useState(false);
  const [editingLot, setEditingLot] = useState<HoldingLot | null>(null);

  const fetchLots = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await accountsApi.getLotsBySecurity(accountId, securityId);
      setLots(resp.data);
    } catch {
      setLots([]);
    } finally {
      setLoading(false);
    }
  }, [accountId, securityId]);

  useEffect(() => {
    fetchLots();
  }, [fetchLots]);

  const openLots = lots.filter((l) => !l.is_closed);
  const closedLots = lots.filter((l) => l.is_closed);

  const handleDeleteLot = async (lotId: string) => {
    if (!window.confirm("Delete this lot?")) return;
    try {
      await accountsApi.deleteLot(accountId, lotId);
      await fetchLots();
    } catch (err) {
      alert(extractApiErrorMessage(err, "Failed to delete lot"));
    }
  };

  if (loading) {
    return <div className="px-6 py-3 text-sm text-tf-text-tertiary">Loading lots...</div>;
  }

  return (
    <div className="bg-tf-bg-elevated px-6 py-4" data-testid="lot-detail-panel">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-tf-text-secondary">
          Lots for {ticker}
        </h4>
        <button
          onClick={() => { setEditingLot(null); setShowLotForm(true); }}
          className="text-xs px-2 py-1 bg-tf-accent-primary text-tf-text-primary rounded hover:bg-tf-accent-hover transition"
          data-testid="add-lot-button"
        >
          Add Lot
        </button>
      </div>

      <LotFormModal
        isOpen={showLotForm}
        lot={editingLot}
        accountId={accountId}
        securityId={securityId}
        ticker={ticker}
        holdingQuantity={holdingQuantity}
        otherLots={openLots.filter((l) => l.id !== editingLot?.id)}
        onClose={() => { setShowLotForm(false); setEditingLot(null); }}
        onSaved={fetchLots}
      />

      {openLots.length === 0 ? (
        <p className="text-sm text-tf-text-tertiary">No open lots. Add one to track cost basis.</p>
      ) : (
        <table className="w-full text-sm" data-testid="open-lots-table">
          <thead>
            <tr className="text-xs text-tf-text-tertiary uppercase">
              <th className="text-left py-1 pr-3">Date</th>
              <th className="text-right py-1 px-3">Qty</th>
              <th className="text-right py-1 px-3">Cost/Unit</th>
              <th className="text-right py-1 px-3">Total Cost</th>
              <th className="text-right py-1 px-3">Gain/Loss</th>
              <th className="text-center py-1 px-3">Source</th>
              <th className="text-right py-1 pl-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {openLots.map((lot) => {
              const totalCost = lot.cost_basis_per_unit * lot.current_quantity;
              const marketValue = marketPrice != null ? marketPrice * lot.current_quantity : null;
              const gainLoss = marketValue != null ? marketValue - totalCost : null;

              return (
                <tr key={lot.id} className="border-t border-tf-border-subtle" data-testid={`lot-row-${lot.id}`}>
                  <td className="py-2 pr-3 text-tf-text-primary">{lot.acquisition_date ?? "Unknown"}</td>
                  <td className="py-2 px-3 text-right text-tf-text-tertiary">
                    {Number(lot.current_quantity).toLocaleString()}
                    {lot.current_quantity !== lot.original_quantity && (
                      <span className="text-xs text-tf-text-tertiary opacity-60 ml-1">
                        /{Number(lot.original_quantity).toLocaleString()}
                      </span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-right text-tf-text-tertiary">
                    ${Number(lot.cost_basis_per_unit).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-2 px-3 text-right text-tf-text-primary">
                    {formatCurrency(totalCost)}
                  </td>
                  <td className="py-2 px-3 text-right">
                    {gainLoss != null ? (
                      <span className={gainLoss >= 0 ? "text-tf-positive" : "text-tf-negative"}>
                        {gainLoss >= 0 ? "+" : "-"}{formatCurrency(Math.abs(gainLoss))}
                      </span>
                    ) : (
                      <span className="text-tf-text-tertiary">&mdash;</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${SOURCE_COLORS[lot.source] || "bg-gray-500/20 text-gray-400"}`}>
                      {SOURCE_LABELS[lot.source] || lot.source}
                    </span>
                  </td>
                  <td className="py-2 pl-3 text-right">
                    {(lot.source === "manual" || lot.source === "inferred" || lot.source === "initial") && (
                      <>
                        <button
                          onClick={() => { setEditingLot(lot); setShowLotForm(true); }}
                          className="text-tf-accent-primary hover:text-tf-accent-hover text-xs mr-2"
                          data-testid={`edit-lot-${lot.id}`}
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeleteLot(lot.id)}
                          className="text-tf-negative hover:text-red-400 text-xs"
                          data-testid={`delete-lot-${lot.id}`}
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {closedLots.length > 0 && (
        <div className="mt-3">
          <button
            onClick={() => setShowClosed(!showClosed)}
            className="text-xs text-tf-text-tertiary hover:text-tf-text-secondary"
            data-testid="toggle-closed-lots"
          >
            {showClosed ? "Hide" : "Show"} {closedLots.length} closed lot{closedLots.length !== 1 ? "s" : ""}
          </button>

          {showClosed && (
            <table className="w-full text-sm mt-2 opacity-60" data-testid="closed-lots-table">
              <tbody>
                {closedLots.map((lot) => (
                  <tr key={lot.id} className="border-t border-tf-border-subtle">
                    <td className="py-1 pr-3 text-tf-text-tertiary">{lot.acquisition_date ?? "Unknown"}</td>
                    <td className="py-1 px-3 text-right text-tf-text-tertiary">
                      {Number(lot.original_quantity).toLocaleString()}
                    </td>
                    <td className="py-1 px-3 text-right text-tf-text-tertiary">
                      ${Number(lot.cost_basis_per_unit).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-1 px-3 text-center">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${SOURCE_COLORS[lot.source] || "bg-gray-500/20 text-gray-400"}`}>
                        {SOURCE_LABELS[lot.source] || lot.source}
                      </span>
                    </td>
                    <td className="py-1 pl-3 text-right text-xs text-tf-text-tertiary">
                      Closed
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
