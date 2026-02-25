import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { assetTypeApi } from "../api/assetTypes";
import { isSyntheticTicker } from "@/utils/ticker";
import { formatCurrency } from "@/utils/format";
import type { AssetTypeHolding, AssetTypeHoldingsDetail } from "../types/assetType";

interface HoldingGroup {
  ticker: string;
  securityName: string | null;
  totalValue: number;
  totalCostBasis: number | null;
  totalGainLoss: number | null;
  groupGainLossPercent: number | null;
  minLotCoverage: number | null;
  holdings: AssetTypeHolding[];
}

export function AssetTypeDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<AssetTypeHoldingsDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      const response = await assetTypeApi.getHoldings(id);
      setData(response.data);
    } catch (err) {
      console.error(err);
      setError("Failed to load asset type details.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const hasCostBasis = useMemo(() => {
    if (!data) return false;
    return data.holdings.some((h) => h.lot_count != null && h.lot_count > 0);
  }, [data]);

  const groupedHoldings = useMemo(() => {
    if (!data) return [];
    const groups = new Map<string, HoldingGroup>();

    for (const h of data.holdings) {
      const existing = groups.get(h.ticker);
      if (existing) {
        existing.totalValue += parseFloat(h.market_value);
        existing.holdings.push(h);
      } else {
        groups.set(h.ticker, {
          ticker: h.ticker,
          securityName: h.security_name,
          totalValue: parseFloat(h.market_value),
          totalCostBasis: null,
          totalGainLoss: null,
          groupGainLossPercent: null,
          minLotCoverage: null,
          holdings: [h],
        });
      }
    }

    // Compute aggregate lot fields per group
    for (const group of groups.values()) {
      let hasCb = false;
      let costBasisSum = 0;
      let gainLossSum = 0;
      let minCoverage: number | null = null;

      for (const h of group.holdings) {
        if (h.lot_count != null && h.lot_count > 0 && h.cost_basis != null) {
          hasCb = true;
          costBasisSum += Number(h.cost_basis);
          if (h.gain_loss != null) {
            gainLossSum += Number(h.gain_loss);
          }
          if (h.lot_coverage != null) {
            const cov = Number(h.lot_coverage);
            if (minCoverage === null || cov < minCoverage) {
              minCoverage = cov;
            }
          }
        }
      }

      if (hasCb) {
        group.totalCostBasis = costBasisSum;
        group.totalGainLoss = gainLossSum;
        group.minLotCoverage = minCoverage;
        if (costBasisSum !== 0) {
          group.groupGainLossPercent = gainLossSum / costBasisSum;
        }
      }
    }

    return Array.from(groups.values())
      .sort((a, b) => b.totalValue - a.totalValue)
      .map(g => ({ ...g, holdings: g.holdings.sort((a, b) => parseFloat(b.market_value) - parseFloat(a.market_value)) }));
  }, [data]);

  const colCount = hasCostBasis ? 6 : 4;

  if (loading) {
    return <div className="p-8">Loading...</div>;
  }

  if (error || !data) {
    return <div className="p-8 text-tf-negative">{error || "Asset type not found"}</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={() => navigate(-1)} className="text-tf-accent-primary hover:underline">
          &larr; Back
        </button>
      </div>
      <div className="bg-tf-bg-surface border border-tf-border-default rounded-lg p-6">
        <div className="flex items-center gap-3">
          <div
            className="w-5 h-5 rounded-full"
            style={{ backgroundColor: data.asset_type_color }}
          />
          <h1 className="text-2xl font-bold text-tf-text-primary">{data.asset_type_name}</h1>
        </div>
        <p className="text-3xl font-bold mt-4 text-tf-positive">
          ${parseFloat(data.total_value).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
        </p>
      </div>

      <div className="bg-tf-bg-surface border border-tf-border-default rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-tf-border-default">
          <thead className="bg-tf-bg-surface">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase">
                Ticker
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase">
                Account
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
            </tr>
          </thead>
          <tbody className="divide-y divide-tf-border-subtle">
            {groupedHoldings.length === 0 ? (
              <tr>
                <td colSpan={colCount} className="px-6 py-4 text-center text-tf-text-tertiary">
                  No holdings found.
                </td>
              </tr>
            ) : (
              groupedHoldings.map((group) =>
                group.holdings.length === 1 ? (
                  <SingleHoldingRow
                    key={group.ticker}
                    group={group}
                    hasCostBasis={hasCostBasis}
                  />
                ) : (
                  <MultiHoldingGroup
                    key={group.ticker}
                    group={group}
                    hasCostBasis={hasCostBasis}
                  />
                )
              )
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CostBasisCell({ costBasis, lotCoverage, lotCount }: {
  costBasis: string | null;
  lotCoverage: string | number | null;
  lotCount: number | null;
}) {
  if (lotCount == null || lotCount <= 0) {
    return <span className="text-tf-text-tertiary">-</span>;
  }
  return (
    <div>
      <div>{formatCurrency(costBasis)}</div>
      {lotCoverage != null && Number(lotCoverage) < 1 && (
        <div className="text-xs text-tf-text-tertiary">
          ~{Math.round(Number(lotCoverage) * 100)}% tracked
        </div>
      )}
    </div>
  );
}

function GainLossCell({ gainLoss, gainLossPercent, lotCount }: {
  gainLoss: string | number | null;
  gainLossPercent: string | number | null;
  lotCount: number | null;
}) {
  if (lotCount == null || lotCount <= 0 || gainLoss == null) {
    return <span className="text-tf-text-tertiary">-</span>;
  }
  const glNum = Number(gainLoss);
  return (
    <div>
      <div className={glNum >= 0 ? "text-tf-positive" : "text-tf-negative"}>
        {formatCurrency(gainLoss)}
      </div>
      {gainLossPercent != null && (
        <div className={`text-xs ${Number(gainLossPercent) >= 0 ? "text-tf-positive" : "text-tf-negative"}`}>
          {Number(gainLossPercent) >= 0 ? "+" : ""}
          {(Number(gainLossPercent) * 100).toFixed(1)}%
        </div>
      )}
    </div>
  );
}

function SingleHoldingRow({ group, hasCostBasis }: { group: HoldingGroup; hasCostBasis: boolean }) {
  const h = group.holdings[0];
  return (
    <tr>
      <td className="px-6 py-4 text-sm font-medium text-tf-text-primary">
        {isSyntheticTicker(group.ticker) ? "\u2014" : group.ticker}
      </td>
      <td className="px-6 py-4 text-sm text-tf-text-primary">
        {group.securityName || "\u2014"}
      </td>
      <td className="px-6 py-4 text-sm text-tf-accent-primary">
        <Link to={`/accounts/${h.account_id}`} className="hover:underline">
          {h.account_name}
        </Link>
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium text-tf-text-primary">
        ${group.totalValue.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}
      </td>
      {hasCostBasis && (
        <>
          <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-primary">
            <CostBasisCell costBasis={h.cost_basis} lotCoverage={h.lot_coverage} lotCount={h.lot_count} />
          </td>
          <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
            <GainLossCell gainLoss={h.gain_loss} gainLossPercent={h.gain_loss_percent} lotCount={h.lot_count} />
          </td>
        </>
      )}
    </tr>
  );
}

function MultiHoldingGroup({ group, hasCostBasis }: { group: HoldingGroup; hasCostBasis: boolean }) {
  return (
    <>
      <tr className="bg-tf-bg-secondary">
        <td className="px-6 py-3 text-sm font-bold text-tf-text-primary">
          {isSyntheticTicker(group.ticker) ? "\u2014" : group.ticker}
        </td>
        <td className="px-6 py-3 text-sm font-bold text-tf-text-primary">
          {group.securityName || "\u2014"}
        </td>
        <td className="px-6 py-3 text-sm text-tf-text-tertiary">All accounts</td>
        <td className="px-6 py-3 whitespace-nowrap text-right text-sm font-bold text-tf-text-primary">
          ${group.totalValue.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
        </td>
        {hasCostBasis && (
          <>
            <td className="px-6 py-3 whitespace-nowrap text-right text-sm font-bold text-tf-text-primary">
              <CostBasisCell
                costBasis={group.totalCostBasis != null ? String(group.totalCostBasis) : null}
                lotCoverage={group.minLotCoverage}
                lotCount={group.totalCostBasis != null ? 1 : null}
              />
            </td>
            <td className="px-6 py-3 whitespace-nowrap text-right text-sm font-bold">
              <GainLossCell
                gainLoss={group.totalGainLoss}
                gainLossPercent={group.groupGainLossPercent}
                lotCount={group.totalCostBasis != null ? 1 : null}
              />
            </td>
          </>
        )}
      </tr>
      {group.holdings.map((h) => (
        <tr key={h.holding_id}>
          <td className="px-6 py-4 text-sm text-tf-text-primary"></td>
          <td className="px-6 py-4 text-sm text-tf-text-tertiary"></td>
          <td className="px-6 py-4 text-sm text-tf-accent-primary">
            <Link to={`/accounts/${h.account_id}`} className="hover:underline">
              {h.account_name}
            </Link>
          </td>
          <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium text-tf-text-primary">
            ${parseFloat(h.market_value).toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </td>
          {hasCostBasis && (
            <>
              <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-primary">
                <CostBasisCell costBasis={h.cost_basis} lotCoverage={h.lot_coverage} lotCount={h.lot_count} />
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                <GainLossCell gainLoss={h.gain_loss} gainLossPercent={h.gain_loss_percent} lotCount={h.lot_count} />
              </td>
            </>
          )}
        </tr>
      ))}
    </>
  );
}
