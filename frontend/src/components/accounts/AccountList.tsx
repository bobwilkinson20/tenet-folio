import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import type { Account } from "../../types";
import { ACCOUNT_TYPE_LABELS } from "../../types";
import type { AccountType } from "../../types";
import { AccountActionsMenu } from "./AccountActionsMenu";
import { getSyncIconState, getSyncTooltip } from "@/utils/syncStatus";
import { formatCurrency } from "@/utils/format";

type SortKey = "name" | "value" | "status" | null;
type SortDirection = "asc" | "desc";

interface SortConfig {
  key: SortKey;
  direction: SortDirection;
}

export interface AccountListProps {
  accounts: Account[];
  loading: boolean;
  onEdit: (account: Account) => void;
  onToggleActive: (account: Account) => void;
  onDelete: (account: Account) => void;
  hideInactive?: boolean;
}

export function AccountList({
  accounts,
  loading,
  onEdit,
  onToggleActive,
  onDelete,
  hideInactive = false,
}: AccountListProps) {
  const [sortConfig, setSortConfig] = useState<SortConfig>({ key: null, direction: "asc" });
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({
    account: 280,
    assetType: 120,
    accountType: 120,
    alloc: 60,
    status: 100,
    value: 150,
    actions: 60,
  });
  const [isResizing, setIsResizing] = useState(false);

  const resizingRef = useRef<{ column: string; startX: number; startWidth: number } | null>(null);

  // Column sorting logic
  const handleSort = (key: SortKey) => {
    setSortConfig((prev) => {
      if (prev.key === key) {
        // Toggle direction or reset
        if (prev.direction === "asc") {
          return { key, direction: "desc" };
        } else {
          return { key: null, direction: "asc" };
        }
      }
      return { key, direction: "asc" };
    });
  };

  const getSortIndicator = (key: SortKey) => {
    if (sortConfig.key !== key) return null;
    return sortConfig.direction === "asc" ? " ▲" : " ▼";
  };

  // Column resizing
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current) return;
      const { column, startX, startWidth } = resizingRef.current;
      const diff = e.clientX - startX;
      const newWidth = Math.max(40, startWidth + diff);
      setColumnWidths((prev) => ({ ...prev, [column]: newWidth }));
    };

    const handleMouseUp = () => {
      if (resizingRef.current) {
        resizingRef.current = null;
        setIsResizing(false);
      }
    };

    if (isResizing) {
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    }

    return () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing]);

  const handleResizeStart = (column: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    resizingRef.current = {
      column,
      startX: e.clientX,
      startWidth: columnWidths[column],
    };
    setIsResizing(true);
  };

  // Filter and sort accounts
  const processedAccounts = (() => {
    let result = [...accounts];

    // Filter inactive if requested
    if (hideInactive) {
      result = result.filter((a) => a.is_active);
    }

    // Sort
    if (sortConfig.key) {
      result.sort((a, b) => {
        let comparison = 0;
        switch (sortConfig.key) {
          case "name":
            comparison = a.name.localeCompare(b.name);
            break;
          case "value": {
            const valA = a.value ? parseFloat(a.value) : 0;
            const valB = b.value ? parseFloat(b.value) : 0;
            comparison = valA - valB;
            break;
          }
          case "status":
            comparison = (a.is_active ? 1 : 0) - (b.is_active ? 1 : 0);
            break;
        }
        return sortConfig.direction === "asc" ? comparison : -comparison;
      });
    }

    return result;
  })();

  if (loading) {
    return <div className="text-center py-8">Loading accounts...</div>;
  }

  if (accounts.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-tf-text-secondary">No accounts found. Sync to get started.</p>
      </div>
    );
  }

  const renderSortableHeader = (
    label: string,
    sortKey: SortKey,
    columnKey: string,
    align: "left" | "right" = "left"
  ) => (
    <th
      className={`relative px-6 py-3 ${align === "right" ? "text-right" : "text-left"} text-xs font-medium text-tf-text-secondary uppercase tracking-wider cursor-pointer hover:bg-tf-bg-elevated select-none overflow-hidden text-ellipsis whitespace-nowrap`}
      style={{ width: columnWidths[columnKey], minWidth: 40 }}
      onClick={() => handleSort(sortKey)}
    >
      <span>
        {label}
        {getSortIndicator(sortKey)}
      </span>
      <div
        className="absolute right-0 top-0 h-full w-2 cursor-col-resize group"
        onMouseDown={(e) => handleResizeStart(columnKey, e)}
      >
        <div className="absolute right-0 top-0 h-full w-0.5 bg-tf-border-default group-hover:bg-tf-accent-primary group-hover:w-1" />
      </div>
    </th>
  );

  const renderNonSortableHeader = (label: string, columnKey: string) => (
    <th
      className="relative px-6 py-3 text-left text-xs font-medium text-tf-text-secondary uppercase tracking-wider select-none overflow-hidden text-ellipsis whitespace-nowrap"
      style={{ width: columnWidths[columnKey], minWidth: 40 }}
    >
      {label}
      <div
        className="absolute right-0 top-0 h-full w-2 cursor-col-resize group"
        onMouseDown={(e) => handleResizeStart(columnKey, e)}
      >
        <div className="absolute right-0 top-0 h-full w-0.5 bg-tf-border-default group-hover:bg-tf-accent-primary group-hover:w-1" />
      </div>
    </th>
  );

  return (
    <div
      className="overflow-auto max-h-[70vh]"
      data-testid="account-list-container"
    >
      <table className="divide-y divide-tf-border-default border border-tf-border-default w-full" style={{ tableLayout: "fixed" }}>
        <thead className="bg-tf-bg-surface sticky top-0 z-10">
          <tr>
            {renderSortableHeader("Account", "name", "account")}
            {renderNonSortableHeader("Asset Type Override", "assetType")}
            {renderNonSortableHeader("Account Type", "accountType")}
            <th
              className="relative px-6 py-3 text-left text-xs font-medium text-tf-text-secondary uppercase tracking-wider select-none overflow-hidden text-ellipsis whitespace-nowrap"
              style={{ width: columnWidths.alloc, minWidth: 40 }}
            >
              <span className="inline-flex items-center gap-1">
                Included
                <span
                  className="inline-flex items-center justify-center h-4 w-4 rounded-full border border-tf-text-tertiary text-tf-text-tertiary text-[10px] font-semibold cursor-help"
                  title="Account is included in portfolio target allocation calculation"
                >
                  i
                </span>
              </span>
              <div
                className="absolute right-0 top-0 h-full w-2 cursor-col-resize group"
                onMouseDown={(e) => handleResizeStart("alloc", e)}
              >
                <div className="absolute right-0 top-0 h-full w-0.5 bg-tf-border-default group-hover:bg-tf-accent-primary group-hover:w-1" />
              </div>
            </th>
            {renderSortableHeader("Status", "status", "status")}
            {renderSortableHeader("Value", "value", "value", "right")}
            <th
              className="relative px-2 py-3 text-center text-xs font-medium text-tf-text-secondary uppercase tracking-wider select-none"
              style={{ width: columnWidths.actions, minWidth: 40 }}
            />
          </tr>
        </thead>
        <tbody className="bg-tf-bg-primary divide-y divide-tf-border-subtle">
          {processedAccounts.map((account) => (
            <tr key={account.id}>
              <td
                className="px-6 py-4 text-sm font-medium text-tf-text-primary overflow-hidden"
                title={account.name}
              >
                <div className="flex items-center gap-2">
                  {(() => {
                    const state = getSyncIconState(account);
                    const tooltip = getSyncTooltip(account);
                    if (state === "green") return (
                      <svg className="w-4 h-4 text-tf-positive flex-shrink-0 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24" data-testid={`sync-ok-${account.id}`} aria-label="Sync OK">
                        <title>{tooltip}</title>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    );
                    if (state === "red") return (
                      <svg className="w-4 h-4 text-tf-negative flex-shrink-0 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24" data-testid={`sync-error-${account.id}`} aria-label="Sync error">
                        <title>{tooltip}</title>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    );
                    if (state === "yellow") return (
                      <svg className="w-4 h-4 text-tf-warning flex-shrink-0 cursor-help" fill="currentColor" viewBox="0 0 24 24" data-testid={`sync-warning-${account.id}`} aria-label="Sync warning">
                        <title>{tooltip}</title>
                        <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" />
                      </svg>
                    );
                    // Manual accounts: green pushpin icon
                    return (
                      <svg className="w-4 h-4 text-tf-positive flex-shrink-0 cursor-help" fill="currentColor" viewBox="0 0 24 24" data-testid={`sync-manual-${account.id}`} aria-label="Manual account">
                        <title>{tooltip}</title>
                        <path d="M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z" />
                      </svg>
                    );
                  })()}
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Link to={`/accounts/${account.id}`} className="text-tf-accent-primary hover:text-tf-accent-hover underline text-ellipsis overflow-hidden">{account.name}</Link>
                      {account.provider_name === "Manual" && (
                        <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-tf-info/10 text-tf-info" data-testid={`manual-badge-${account.id}`}>
                          Manual
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-tf-text-tertiary">{account.institution_name || account.provider_name}</p>
                  </div>
                </div>
              </td>
              <td className="px-6 py-4 text-sm overflow-hidden">
                {account.assigned_asset_class_id && account.assigned_asset_class_name ? (
                  <span className="inline-flex items-center gap-1.5">
                    {account.assigned_asset_class_color && (
                      <span
                        className="inline-block h-2.5 w-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: account.assigned_asset_class_color }}
                      />
                    )}
                    <span className="text-sm text-tf-text-secondary">{account.assigned_asset_class_name}</span>
                  </span>
                ) : (
                  <span className="text-sm text-tf-text-tertiary">-</span>
                )}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm overflow-hidden">
                {account.account_type ? (
                  <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-tf-accent-muted text-tf-accent-hover" data-testid={`account-type-badge-${account.id}`}>
                    {ACCOUNT_TYPE_LABELS[account.account_type as AccountType] ?? account.account_type}
                  </span>
                ) : (
                  <span className="text-tf-text-tertiary">-</span>
                )}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-center overflow-hidden" data-testid={`alloc-${account.id}`}>
                {account.include_in_allocation ? (
                  <svg className="w-4 h-4 text-tf-positive mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <span className="text-tf-text-tertiary">-</span>
                )}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm overflow-hidden">
                <div className="flex flex-col gap-1">
                  <span
                    className={`px-2 py-1 rounded-full text-xs font-semibold self-start ${
                      account.is_active
                        ? "bg-tf-positive/10 text-tf-positive"
                        : "bg-tf-bg-elevated text-tf-text-secondary"
                    }`}
                  >
                    {account.is_active ? "Active" : "Inactive"}
                  </span>
                  {!account.is_active && account.superseded_by_name && (
                    <span
                      className="text-xs text-tf-text-tertiary truncate max-w-[120px]"
                      title={`Replaced by: ${account.superseded_by_name}`}
                      data-testid={`superseded-by-badge-${account.id}`}
                    >
                      &rarr; {account.superseded_by_name}
                    </span>
                  )}
                </div>
              </td>
              <td
                className="px-6 py-4 whitespace-nowrap text-sm text-right font-medium text-tf-text-primary overflow-hidden text-ellipsis"
              >
                {formatCurrency(account.value)}
              </td>
              <td className="px-2 py-4 whitespace-nowrap text-sm overflow-visible text-center">
                <AccountActionsMenu
                  account={account}
                  onEdit={onEdit}
                  onToggleActive={onToggleActive}
                  onDelete={onDelete}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
