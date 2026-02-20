import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { portfolioApi } from "@/api";
import { useFetch } from "@/hooks";
import { formatCurrency } from "@/utils/format";

const currentYear = new Date().getFullYear();
const yearOptions = Array.from({ length: 6 }, (_, i) => currentYear - i);

export function RealizedGainsPage() {
  const navigate = useNavigate();
  const [year, setYear] = useState<number | undefined>(currentYear);

  const fetchGains = useCallback(
    () => portfolioApi.getRealizedGains(year != null ? { year } : undefined),
    [year]
  );
  const { data, loading, refetch } = useFetch(fetchGains);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const totalGainLoss = parseFloat(data?.total_realized_gain_loss ?? "0");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
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
          <h1 className="text-2xl font-bold">Realized Gains</h1>
        </div>

        <select
          value={year ?? "all"}
          onChange={(e) =>
            setYear(e.target.value === "all" ? undefined : Number(e.target.value))
          }
          className="bg-tf-bg-elevated border border-tf-border-subtle rounded-lg px-3 py-1.5 text-sm text-tf-text-primary"
        >
          {yearOptions.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
          <option value="all">All time</option>
        </select>
      </div>

      {/* Summary */}
      <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-tf-text-tertiary">
              {data?.items.length ?? 0} disposal{(data?.items.length ?? 0) !== 1 ? "s" : ""}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-tf-text-tertiary mb-1">
              Total Realized G/L
            </p>
            <p
              className={`text-2xl font-bold ${
                totalGainLoss >= 0 ? "text-tf-positive" : "text-tf-negative"
              }`}
            >
              {formatCurrency(data?.total_realized_gain_loss)}
            </p>
          </div>
        </div>
      </div>

      {/* Table */}
      {loading && !data ? (
        <div className="flex items-center justify-center h-32">
          <p className="text-tf-text-tertiary">Loading...</p>
        </div>
      ) : data && data.items.length > 0 ? (
        <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-tf-border-subtle bg-tf-bg-elevated/50">
                  <th className="text-left px-4 py-3 font-medium text-tf-text-secondary">
                    Date
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-tf-text-secondary">
                    Security
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-tf-text-secondary">
                    Account
                  </th>
                  <th className="text-right px-4 py-3 font-medium text-tf-text-secondary">
                    Qty
                  </th>
                  <th className="text-right px-4 py-3 font-medium text-tf-text-secondary">
                    Proceeds
                  </th>
                  <th className="text-right px-4 py-3 font-medium text-tf-text-secondary">
                    Cost
                  </th>
                  <th className="text-right px-4 py-3 font-medium text-tf-text-secondary">
                    Gain/Loss
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => {
                  const gl = parseFloat(item.gain_loss);
                  return (
                    <tr
                      key={item.disposal_id}
                      className="border-b border-tf-border-subtle last:border-b-0 hover:bg-tf-bg-elevated/30"
                    >
                      <td className="px-4 py-3 text-tf-text-primary">
                        {new Date(item.disposal_date + "T00:00:00").toLocaleDateString(
                          "en-US",
                          { month: "short", day: "numeric", year: "numeric" }
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-tf-text-primary font-medium">
                          {item.ticker}
                        </span>
                        {item.security_name && (
                          <span className="text-tf-text-tertiary ml-2 text-xs">
                            {item.security_name}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-tf-text-secondary">
                        {item.account_name}
                      </td>
                      <td className="px-4 py-3 text-right text-tf-text-primary tabular-nums">
                        {parseFloat(item.quantity).toLocaleString(undefined, {
                          maximumFractionDigits: 4,
                        })}
                      </td>
                      <td className="px-4 py-3 text-right text-tf-text-primary tabular-nums">
                        {formatCurrency(item.total_proceeds)}
                      </td>
                      <td className="px-4 py-3 text-right text-tf-text-primary tabular-nums">
                        {formatCurrency(item.total_cost)}
                      </td>
                      <td
                        className={`px-4 py-3 text-right font-medium tabular-nums ${
                          gl >= 0 ? "text-tf-positive" : "text-tf-negative"
                        }`}
                      >
                        {formatCurrency(item.gain_loss)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl p-12 text-center">
          <p className="text-tf-text-tertiary">
            No realized gains{year != null ? ` in ${year}` : ""}.
          </p>
        </div>
      )}
    </div>
  );
}
