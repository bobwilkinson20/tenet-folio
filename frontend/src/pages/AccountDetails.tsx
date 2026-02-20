import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { accountsApi } from "../api/accounts";
import { ActivityList } from "../components/activities/ActivityList";
import { HoldingFormModal } from "../components/accounts/HoldingFormModal";
import { LotDetailPanel } from "../components/lots/LotDetailPanel";
import { formatCurrency } from "@/utils/format";
import { isSyntheticTicker, isCashTicker } from "@/utils/ticker";
import { useAccountDetails } from "../hooks/useAccountDetails";
import type { Holding } from "../types/sync_session";

export function AccountDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { account, holdings, activities, loading, error, refetchHoldings } =
    useAccountDetails(id);
  const [showHoldingForm, setShowHoldingForm] = useState(false);
  const [editingHolding, setEditingHolding] = useState<Holding | null>(null);
  const [expandedHoldings, setExpandedHoldings] = useState<Set<string>>(new Set());

  const handleDeleteHolding = async (holdingId: string) => {
    if (!id || !window.confirm("Delete this holding?")) return;
    try {
      await accountsApi.deleteHolding(id, holdingId);
      await refetchHoldings();
    } catch (err) {
      console.error("Failed to delete holding:", err);
    }
  };

  if (loading) {
    return <div className="p-8">Loading...</div>;
  }

  if (error || !account) {
    return <div className="p-8 text-tf-negative">{error ? "Failed to load account details." : "Account not found"}</div>;
  }

  const isManual = account.provider_name === "Manual";
  const totalValue = holdings.reduce((sum, h) => sum + Number(h.market_value ?? h.snapshot_value), 0);
  const cashBalance = holdings
    .filter((h) => isCashTicker(h.ticker))
    .reduce((sum, h) => sum + Number(h.market_value ?? h.snapshot_value), 0);
  const displayHoldings = holdings.filter((h) => !isCashTicker(h.ticker));
  const hasCostBasis = displayHoldings.some(
    (h) => h.lot_count != null && h.lot_count > 0
  );
  const baseColCount = 4 + (hasCostBasis ? 2 : 0) + (isManual ? 1 : 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={() => navigate(-1)} className="text-tf-accent-primary hover:underline">
          &larr; Back
        </button>
      </div>
      <div className="bg-tf-bg-surface border border-tf-border-default rounded-lg p-6">
        <h1 className="text-2xl font-bold text-tf-text-primary">{account.name}</h1>
        <p className="text-tf-text-tertiary">
          {account.institution_name || account.provider_name}
        </p>
        <p className="text-3xl font-bold mt-4 text-tf-positive">
          ${totalValue.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
        </p>
        {cashBalance !== 0 && (
          <p className={`text-sm mt-1 ${cashBalance < 0 ? "text-tf-negative" : "text-tf-text-tertiary"}`}>
            Cash: ${cashBalance.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </p>
        )}
      </div>

      {isManual && (
        <div className="flex justify-end">
          <button
            onClick={() => {
              setEditingHolding(null);
              setShowHoldingForm(true);
            }}
            className="px-4 py-2 bg-tf-accent-primary text-tf-text-primary rounded hover:bg-tf-accent-hover transition text-sm font-medium"
            data-testid="add-holding-button"
          >
            Add Holding
          </button>
        </div>
      )}

      <HoldingFormModal
        isOpen={showHoldingForm}
        holding={editingHolding}
        accountId={id || ""}
        existingTickers={holdings.map((h) => h.ticker.toUpperCase())}
        onClose={() => {
          setShowHoldingForm(false);
          setEditingHolding(null);
        }}
        onSaved={refetchHoldings}
      />

      <div className="bg-tf-bg-surface border border-tf-border-default rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-tf-border-default">
          <thead className="bg-tf-bg-surface">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase">
                Security
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase">
                Quantity
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase">
                Price
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase">
                Value
              </th>
              {hasCostBasis && (
                <>
                  <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase">
                    Cost Basis
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase">
                    Gain/Loss
                  </th>
                </>
              )}
              {isManual && (
                <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase">
                  Actions
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-tf-border-subtle">
            {displayHoldings.length === 0 ? (
              <tr>
                <td
                  colSpan={baseColCount}
                  className="px-6 py-4 text-center text-tf-text-tertiary"
                >
                  {isManual
                    ? "No holdings yet. Add one to get started."
                    : "No holdings found. Sync required."}
                </td>
              </tr>
            ) : (
              displayHoldings.map((h) => {
                const isExpanded = expandedHoldings.has(h.id);
                const canExpand = h.lot_count != null && h.lot_count > 0;
                const toggleExpand = () => {
                  setExpandedHoldings((prev) => {
                    const next = new Set(prev);
                    if (next.has(h.id)) next.delete(h.id);
                    else next.add(h.id);
                    return next;
                  });
                };

                return (
                <React.Fragment key={h.id}>
                <tr
                  className={canExpand ? "cursor-pointer hover:bg-tf-bg-elevated/50" : ""}
                  onClick={canExpand ? toggleExpand : undefined}
                >
                  <td className="px-6 py-4 text-sm text-tf-text-primary">
                    <div className="flex items-center gap-2">
                      {canExpand && (
                        <span className="text-tf-text-tertiary text-xs" data-testid={`expand-lots-${h.id}`}>
                          {isExpanded ? "\u25BC" : "\u25B6"}
                        </span>
                      )}
                      {isSyntheticTicker(h.ticker) ? (
                        <div>
                          <div className="font-medium">
                            {h.security_name || "Unknown"}
                          </div>
                        </div>
                      ) : (
                        <div>
                          <div className="font-medium">{h.ticker}</div>
                          {h.security_name && (
                            <div className="text-xs text-tf-text-tertiary">
                              {h.security_name}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-tertiary">
                    {h.ticker.startsWith("_MAN:") ? "-" : Number(h.quantity).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-tertiary">
                    {h.ticker.startsWith("_MAN:") ? "-" : `$${Number(h.market_price ?? h.snapshot_price).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                    })}`}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium text-tf-text-primary">
                    ${Number(h.market_value ?? h.snapshot_value).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                    })}
                  </td>
                  {hasCostBasis && (
                    <>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-primary">
                        {h.lot_count != null && h.lot_count > 0 ? (
                          <div>
                            <div>{formatCurrency(h.cost_basis)}</div>
                            {h.lot_coverage != null && Number(h.lot_coverage) < 1 && (
                              <div className="text-xs text-tf-text-tertiary">
                                ~{Math.round(Number(h.lot_coverage) * 100)}% tracked
                              </div>
                            )}
                          </div>
                        ) : (
                          <span className="text-tf-text-tertiary">-</span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                        {h.lot_count != null && h.lot_count > 0 && h.gain_loss != null ? (
                          <div>
                            <div className={Number(h.gain_loss) >= 0 ? "text-tf-positive" : "text-tf-negative"}>
                              {formatCurrency(h.gain_loss)}
                            </div>
                            {h.gain_loss_percent != null && (
                              <div className={`text-xs ${Number(h.gain_loss_percent) >= 0 ? "text-tf-positive" : "text-tf-negative"}`}>
                                {Number(h.gain_loss_percent) >= 0 ? "+" : ""}
                                {(Number(h.gain_loss_percent) * 100).toFixed(1)}%
                              </div>
                            )}
                          </div>
                        ) : (
                          <span className="text-tf-text-tertiary">-</span>
                        )}
                      </td>
                    </>
                  )}
                  {isManual && (
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingHolding(h);
                          setShowHoldingForm(true);
                        }}
                        className="text-tf-accent-primary hover:text-tf-accent-hover mr-3"
                        data-testid={`edit-holding-${h.id}`}
                      >
                        Edit
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteHolding(h.id);
                        }}
                        className="text-tf-negative hover:text-red-400"
                        data-testid={`delete-holding-${h.id}`}
                      >
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
                {isExpanded && h.security_id && (
                  <tr key={`${h.id}-lots`}>
                    <td colSpan={baseColCount}>
                      <LotDetailPanel
                        accountId={id || ""}
                        securityId={h.security_id}
                        ticker={h.ticker}
                        marketPrice={h.market_price != null ? Number(h.market_price) : undefined}
                        holdingQuantity={Number(h.quantity)}
                      />
                    </td>
                  </tr>
                )}
                </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div>
        <h2 className="text-lg font-semibold text-tf-text-primary mb-3">Activity</h2>
        <ActivityList activities={activities} loading={loading} />
      </div>
    </div>
  );
}
