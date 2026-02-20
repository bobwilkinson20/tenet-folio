import type { ReactNode } from "react";
import type { CashFlowAccountSummary } from "@/types/activity";
import { formatCurrency } from "@/utils/format";

interface Props {
  summary: CashFlowAccountSummary;
  isExpanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}

export function AccountSummaryRow({ summary, isExpanded, onToggle, children }: Props) {
  return (
    <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-xl overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-tf-bg-elevated/30 transition-colors"
        data-testid={`account-row-${summary.account_id}`}
      >
        <div className="flex items-center gap-3">
          <span className="text-tf-text-tertiary text-sm">
            {isExpanded ? "\u25BC" : "\u25B6"}
          </span>
          <span className="font-medium text-tf-text-primary">
            {summary.account_name}
          </span>
          {summary.unreviewed_count > 0 && (
            <span
              className="bg-tf-accent-primary/20 text-tf-accent-hover text-xs font-medium px-2 py-0.5 rounded-full"
              data-testid={`unreviewed-badge-${summary.account_id}`}
            >
              {summary.unreviewed_count} unreviewed
            </span>
          )}
        </div>

        <div className="flex items-center gap-6 text-sm tabular-nums">
          <div>
            <span className="text-tf-text-tertiary mr-1">In:</span>
            <span className="text-tf-positive">{formatCurrency(summary.total_inflows)}</span>
          </div>
          <div>
            <span className="text-tf-text-tertiary mr-1">Out:</span>
            <span className="text-tf-negative">{formatCurrency(summary.total_outflows)}</span>
          </div>
          <div>
            <span className="text-tf-text-tertiary mr-1">Net:</span>
            <span className="text-tf-text-primary">{formatCurrency(summary.net_flow)}</span>
          </div>
          <span className="text-tf-text-tertiary">
            {summary.activity_count} activit{summary.activity_count === 1 ? "y" : "ies"}
          </span>
        </div>
      </button>

      {isExpanded && (
        <div className="border-t border-tf-border-subtle">
          {children}
        </div>
      )}
    </div>
  );
}
