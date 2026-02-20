/**
 * Warning banner for accounts with valuation issues (missing, partial, stale).
 */

import type { AccountSummary } from "@/types";

interface Props {
  accounts: AccountSummary[];
}

function statusDescription(status: string): string {
  switch (status) {
    case "missing":
      return "missing valuation data (shown as $0)";
    case "partial":
      return "some holdings missing valuation data";
    case "stale":
      return "valuation data may be outdated";
    default:
      return "valuation issue";
  }
}

export function ValuationWarning({ accounts }: Props) {
  const problemAccounts = accounts.filter(
    (a): a is AccountSummary & { valuation_status: "partial" | "missing" | "stale" } =>
      a.valuation_status !== null && a.valuation_status !== "ok",
  );

  if (problemAccounts.length === 0) {
    return null;
  }

  const hasMissing = problemAccounts.some(
    (a) => a.valuation_status === "missing",
  );

  const borderClass = hasMissing
    ? "bg-tf-negative/10 border-tf-negative/20"
    : "bg-tf-warning/10 border-tf-warning/20";
  const textClass = hasMissing ? "text-tf-negative" : "text-tf-warning";

  return (
    <div
      className={`${borderClass} border rounded-lg p-4`}
      data-testid="valuation-warning"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          <svg
            className={`w-6 h-6 ${textClass}`}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className={`text-sm font-medium ${textClass}`}>
            Valuation issues detected
          </h3>
          <ul className={`mt-2 text-sm ${textClass} list-disc list-inside`}>
            {problemAccounts.map((a) => (
              <li key={a.id}>
                {a.name}: {statusDescription(a.valuation_status)}
              </li>
            ))}
          </ul>
          <p className={`mt-2 text-sm ${textClass}`}>
            Try re-syncing your accounts to resolve this.
          </p>
        </div>
      </div>
    </div>
  );
}
