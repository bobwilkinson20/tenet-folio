import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { assetTypeApi } from "../api/assetTypes";
import { isSyntheticTicker } from "@/utils/ticker";
import type { AssetTypeHolding, AssetTypeHoldingsDetail } from "../types/assetType";

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

  const groupedHoldings = useMemo(() => {
    if (!data) return [];
    const groups = new Map<string, { ticker: string; securityName: string | null; totalValue: number; holdings: AssetTypeHolding[] }>();

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
          holdings: [h],
        });
      }
    }

    return Array.from(groups.values())
      .sort((a, b) => b.totalValue - a.totalValue)
      .map(g => ({ ...g, holdings: g.holdings.sort((a, b) => parseFloat(b.market_value) - parseFloat(a.market_value)) }));
  }, [data]);

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
            </tr>
          </thead>
          <tbody className="divide-y divide-tf-border-subtle">
            {groupedHoldings.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-6 py-4 text-center text-tf-text-tertiary">
                  No holdings found.
                </td>
              </tr>
            ) : (
              groupedHoldings.map((group) =>
                group.holdings.length === 1 ? (
                  <tr key={group.ticker}>
                    <td className="px-6 py-4 text-sm font-medium text-tf-text-primary">
                      {isSyntheticTicker(group.ticker) ? "—" : group.ticker}
                    </td>
                    <td className="px-6 py-4 text-sm text-tf-text-primary">
                      {group.securityName || "—"}
                    </td>
                    <td className="px-6 py-4 text-sm text-tf-accent-primary">
                      <Link to={`/accounts/${group.holdings[0].account_id}`} className="hover:underline">
                        {group.holdings[0].account_name}
                      </Link>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium text-tf-text-primary">
                      ${group.totalValue.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </td>
                  </tr>
                ) : (
                  <Fragment key={group.ticker}>
                    <tr className="bg-tf-bg-secondary">
                      <td className="px-6 py-3 text-sm font-bold text-tf-text-primary">
                        {isSyntheticTicker(group.ticker) ? "—" : group.ticker}
                      </td>
                      <td className="px-6 py-3 text-sm font-bold text-tf-text-primary">
                        {group.securityName || "—"}
                      </td>
                      <td className="px-6 py-3 text-sm text-tf-text-tertiary">All accounts</td>
                      <td className="px-6 py-3 whitespace-nowrap text-right text-sm font-bold text-tf-text-primary">
                        ${group.totalValue.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </td>
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
                      </tr>
                    ))}
                  </Fragment>
                )
              )
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
