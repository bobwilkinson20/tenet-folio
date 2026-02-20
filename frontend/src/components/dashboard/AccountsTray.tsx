import { Link } from "react-router-dom";
import type { AccountSummary } from "../../types";
import { getSyncIconState, getSyncTooltip } from "@/utils/syncStatus";
import { formatCurrency } from "@/utils/format";

interface AccountsTrayProps {
  accounts: AccountSummary[];
  isOpen: boolean;
  selectedAccountIds: string[] | null;
  onSelectionChange: (ids: string[] | null) => void;
}

function SyncIcon({ account }: { account: AccountSummary }) {
  const state = getSyncIconState(account);
  const tooltip = getSyncTooltip(account);

  if (state === "green")
    return (
      <svg
        className="w-4 h-4 text-tf-positive flex-shrink-0"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        data-testid={`tray-sync-ok-${account.id}`}
        aria-label="Sync OK"
      >
        <title>{tooltip}</title>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M5 13l4 4L19 7"
        />
      </svg>
    );
  if (state === "red")
    return (
      <svg
        className="w-4 h-4 text-tf-negative flex-shrink-0"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        data-testid={`tray-sync-error-${account.id}`}
        aria-label="Sync error"
      >
        <title>{tooltip}</title>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M6 18L18 6M6 6l12 12"
        />
      </svg>
    );
  if (state === "yellow")
    return (
      <svg
        className="w-4 h-4 text-tf-warning flex-shrink-0"
        fill="currentColor"
        viewBox="0 0 24 24"
        data-testid={`tray-sync-warning-${account.id}`}
        aria-label="Sync warning"
      >
        <title>{tooltip}</title>
        <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" />
      </svg>
    );
  // gray — Manual accounts
  return (
    <svg
      className="w-4 h-4 text-tf-positive flex-shrink-0"
      fill="currentColor"
      viewBox="0 0 24 24"
      data-testid={`tray-sync-manual-${account.id}`}
      aria-label="Manual account"
    >
      <title>{tooltip}</title>
      <path d="M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z" />
    </svg>
  );
}

interface GroupedAccounts {
  institution: string;
  accounts: AccountSummary[];
}

function groupByInstitution(accounts: AccountSummary[]): GroupedAccounts[] {
  const map = new Map<string, AccountSummary[]>();
  for (const acct of accounts) {
    const key = acct.institution_name || acct.provider_name;
    const group = map.get(key);
    if (group) {
      group.push(acct);
    } else {
      map.set(key, [acct]);
    }
  }

  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([institution, accts]) => ({
      institution,
      accounts: [...accts].sort((a, b) => a.name.localeCompare(b.name)),
    }));
}

export function AccountsTray({
  accounts,
  isOpen,
  selectedAccountIds,
  onSelectionChange,
}: AccountsTrayProps) {
  const groups = groupByInstitution(accounts);

  const allAccountIds = accounts.map((a) => a.id);

  const isSelected = (id: string) =>
    selectedAccountIds === null || selectedAccountIds.includes(id);

  const handleToggle = (id: string) => {
    if (selectedAccountIds === null) {
      // Transitioning from "all selected" to explicit list with one removed
      onSelectionChange(allAccountIds.filter((aid) => aid !== id));
    } else if (selectedAccountIds.includes(id)) {
      // Uncheck: remove from list
      const next = selectedAccountIds.filter((aid) => aid !== id);
      onSelectionChange(next.length === 0 ? [] : next);
    } else {
      // Check: add to list, if all are now selected, go back to null
      const next = [...selectedAccountIds, id];
      onSelectionChange(next.length === allAccountIds.length ? null : next);
    }
  };

  const handleSelectAll = () => onSelectionChange(null);
  const handleSelectNone = () => onSelectionChange([]);

  return (
    <div
      className={`flex-shrink-0 border-r border-tf-border-subtle bg-tf-bg-surface overflow-hidden transition-[width] duration-150 ease-in-out ${
        isOpen ? "w-72" : "w-0"
      }`}
      data-testid="accounts-tray"
    >
      <div className="w-72 h-full overflow-y-auto">
        {/* Header */}
        <div className="px-4 py-3 border-b border-tf-border-subtle flex items-center justify-between">
          <h3 className="text-sm font-semibold text-tf-text-primary uppercase tracking-wider">
            Accounts
          </h3>
          <div className="flex gap-2 text-xs">
            <button
              onClick={handleSelectAll}
              className="text-tf-accent hover:text-tf-text-primary"
              data-testid="tray-select-all"
            >
              All
            </button>
            <button
              onClick={handleSelectNone}
              className="text-tf-accent hover:text-tf-text-primary"
              data-testid="tray-select-none"
            >
              None
            </button>
          </div>
        </div>

        {/* Account list */}
        {groups.length === 0 ? (
          <p className="text-tf-text-tertiary text-sm text-center py-8">
            No accounts found.
          </p>
        ) : (
          groups.map((group) => (
            <div key={group.institution}>
              <div className="px-4 py-2 bg-tf-bg-primary text-xs font-semibold text-tf-text-tertiary uppercase tracking-wider sticky top-0">
                {group.institution}
              </div>
              {group.accounts.map((account) => (
                <div
                  key={account.id}
                  className="flex items-center gap-2 px-4 py-3 hover:bg-tf-bg-elevated border-b border-tf-border-subtle"
                  data-testid={`tray-account-${account.id}`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected(account.id)}
                    onChange={() => handleToggle(account.id)}
                    className="w-4 h-4 flex-shrink-0 accent-tf-accent-primary cursor-pointer"
                    data-testid={`tray-checkbox-${account.id}`}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <Link
                    to={`/accounts/${account.id}`}
                    className="flex items-center gap-2 flex-1 min-w-0"
                  >
                    <SyncIcon account={account} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-tf-text-primary truncate">
                        {account.name}
                      </p>
                      <p className="text-xs text-tf-text-tertiary truncate">
                        {account.institution_name || account.provider_name}
                      </p>
                    </div>
                    <span className="text-sm font-medium text-tf-text-primary whitespace-nowrap">
                      {formatCurrency(account.value)}
                    </span>
                  </Link>
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
