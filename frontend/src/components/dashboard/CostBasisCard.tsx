import { useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { portfolioApi } from "@/api";
import { useFetch } from "@/hooks";
import { formatCurrency } from "@/utils/format";

interface CostBasisCardProps {
  accountIds?: string;
}

export function CostBasisCard({ accountIds }: CostBasisCardProps) {
  const fetchCostBasis = useCallback(
    () => portfolioApi.getCostBasis(accountIds ? { account_ids: accountIds } : undefined),
    [accountIds]
  );
  const { data, refetch } = useFetch(fetchCostBasis);

  useEffect(() => {
    refetch();
  }, [refetch]);

  if (!data || !data.has_lots) {
    return null;
  }

  const unrealized = parseFloat(data.total_unrealized_gain_loss ?? "0");
  const realized = parseFloat(data.total_realized_gain_loss_ytd ?? "0");

  return (
    <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-tf-text-secondary">
          Cost Basis
        </h3>
        <div className="flex items-center gap-3 text-xs text-tf-text-tertiary">
          <span>{data.lot_count} lots</span>
          {data.coverage_percent != null && (
            <span>{data.coverage_percent.toFixed(0)}% coverage</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div>
          <p className="text-xs text-tf-text-tertiary mb-1">Unrealized G/L</p>
          <p
            className={`text-xl font-semibold ${
              unrealized >= 0 ? "text-tf-positive" : "text-tf-negative"
            }`}
          >
            {formatCurrency(data.total_unrealized_gain_loss)}
          </p>
        </div>
        <div>
          <p className="text-xs text-tf-text-tertiary mb-1">
            Realized G/L (YTD)
          </p>
          <p
            className={`text-xl font-semibold ${
              realized >= 0 ? "text-tf-positive" : "text-tf-negative"
            }`}
          >
            {formatCurrency(data.total_realized_gain_loss_ytd)}
          </p>
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-tf-border-subtle">
        <Link
          to="/realized-gains"
          className="text-sm text-tf-accent hover:text-tf-text-primary"
        >
          View realized gains →
        </Link>
      </div>
    </div>
  );
}
