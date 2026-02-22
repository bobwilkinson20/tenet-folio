import { useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { portfolioApi } from "@/api";
import { useFetch } from "@/hooks";
import { formatPercent } from "@/utils/format";
import type { PeriodReturn } from "@/types/portfolio";

const PERIODS = "1D,1M,QTD,3M,YTD,1Y";

function IrrCell({ period }: { period: PeriodReturn }) {
  const irrValue = period.irr !== null ? parseFloat(period.irr) : null;
  const colorClass =
    irrValue === null
      ? "text-tf-text-tertiary"
      : irrValue >= 0
        ? "text-tf-positive"
        : "text-tf-negative";

  return (
    <td className={`px-4 py-3 text-right font-medium tabular-nums ${colorClass}`}>
      {formatPercent(period.irr)}
    </td>
  );
}

export function ReturnsPage() {
  const navigate = useNavigate();

  const fetchReturns = useCallback(
    () => portfolioApi.getReturns({ periods: PERIODS, include_inactive: true }),
    []
  );
  const { data, loading, refetch } = useFetch(fetchReturns);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const portfolio = data?.portfolio;
  const accounts = data?.accounts ?? [];
  const periodLabels = portfolio?.periods.map((p) => p.period) ??
    PERIODS.split(",");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate(-1)}
          className="p-1.5 rounded-md text-tf-text-tertiary hover:text-tf-text-primary hover:bg-tf-bg-elevated transition-colors"
          aria-label="Go back"
        >
          <svg
            className="w-5 h-5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="text-2xl font-bold">Returns</h1>
      </div>

      {loading && !data ? (
        <div className="flex items-center justify-center h-32">
          <p className="text-tf-text-tertiary">Loading...</p>
        </div>
      ) : (
        <>
          {/* Portfolio Summary */}
          {portfolio && (
            <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl p-6">
              <h2 className="text-sm font-medium text-tf-text-secondary mb-4">
                Portfolio Returns (IRR)
              </h2>
              <div className="grid grid-cols-6 gap-4">
                {portfolio.periods.map((period) => {
                  const irrValue =
                    period.irr !== null ? parseFloat(period.irr) : null;
                  const colorClass =
                    irrValue === null
                      ? "text-tf-text-tertiary"
                      : irrValue >= 0
                        ? "text-tf-positive"
                        : "text-tf-negative";

                  return (
                    <div key={period.period} className="text-center">
                      <p className="text-xs text-tf-text-tertiary mb-1">
                        {period.period}
                      </p>
                      <p
                        className={`text-2xl font-bold tabular-nums ${colorClass}`}
                      >
                        {formatPercent(period.irr)}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Per-Account Breakdown */}
          {accounts.length > 0 && (
            <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl overflow-hidden">
              <div className="px-6 py-4 border-b border-tf-border-subtle">
                <h2 className="text-sm font-medium text-tf-text-secondary">
                  Account Returns (IRR)
                </h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-tf-border-subtle bg-tf-bg-elevated/50">
                      <th className="text-left px-4 py-3 font-medium text-tf-text-secondary">
                        Account
                      </th>
                      {periodLabels.map((label) => (
                        <th
                          key={label}
                          className="text-right px-4 py-3 font-medium text-tf-text-secondary"
                        >
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {accounts.map((account) => (
                      <tr
                        key={account.scope_id}
                        className="border-b border-tf-border-subtle last:border-b-0 hover:bg-tf-bg-elevated/30"
                      >
                        <td className="px-4 py-3 text-tf-text-primary font-medium">
                          <span className="inline-flex items-center gap-1.5">
                            {account.scope_name}
                            {account.chained_from && account.chained_from.length > 0 && (
                              <span
                                title={`Includes history from: ${account.chained_from.join(", ")}`}
                                className="text-tf-text-tertiary"
                              >
                                <svg
                                  className="w-4 h-4"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth={2}
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                >
                                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                                </svg>
                              </span>
                            )}
                          </span>
                        </td>
                        {account.periods.map((period) => (
                          <IrrCell key={period.period} period={period} />
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Empty state */}
          {!portfolio && accounts.length === 0 && (
            <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl p-12 text-center">
              <p className="text-tf-text-tertiary">
                No returns data available. Sync your accounts to get started.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
