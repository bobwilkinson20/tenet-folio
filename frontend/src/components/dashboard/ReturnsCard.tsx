import { useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { portfolioApi } from "@/api";
import { useFetch } from "@/hooks";
import { formatPercent } from "@/utils/format";

const PERIODS = "1D,1M,QTD,3M,YTD,1Y";

interface ReturnsCardProps {
  accountIds?: string;
}

export function ReturnsCard({ accountIds }: ReturnsCardProps) {
  const fetchReturns = useCallback(
    () => portfolioApi.getReturns({
      scope: "portfolio",
      periods: PERIODS,
      account_ids: accountIds,
    }),
    [accountIds]
  );
  const { data, refetch } = useFetch(fetchReturns);

  useEffect(() => {
    refetch();
  }, [refetch]);

  if (!data || !data.portfolio) {
    return null;
  }

  const { periods } = data.portfolio;

  if (periods.length === 0) {
    return null;
  }

  return (
    <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-tf-text-secondary">
          Returns (IRR)
        </h3>
      </div>

      <div className="grid grid-cols-6 gap-4">
        {periods.map((period) => {
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
              <p className={`text-lg font-semibold tabular-nums ${colorClass}`}>
                {formatPercent(period.irr)}
              </p>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-3 border-t border-tf-border-subtle">
        <Link
          to="/returns"
          className="text-sm text-tf-accent hover:text-tf-text-primary"
        >
          View returns detail →
        </Link>
      </div>
    </div>
  );
}
