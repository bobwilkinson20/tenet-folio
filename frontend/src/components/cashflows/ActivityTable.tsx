import { useState, useRef, useEffect } from "react";
import { formatCurrency } from "@/utils/format";
import { accountsApi } from "@/api/accounts";
import { extractApiErrorMessage } from "@/utils/errors";
import type { Activity, ActivityUpdate } from "@/types";

const CASH_FLOW_TYPES = new Set([
  "deposit",
  "withdrawal",
  "transfer_in",
  "transfer_out",
]);

const ACTIVITY_TYPES = [
  "deposit",
  "withdrawal",
  "transfer_in",
  "transfer_out",
  "buy",
  "sell",
  "dividend",
  "interest",
  "fee",
  "tax",
  "other",
];

function directionLabel(type: string): { label: string; color: string } {
  if (["deposit", "transfer_in", "dividend", "interest"].includes(type)) {
    return { label: "IN", color: "text-tf-positive" };
  }
  if (["withdrawal", "transfer_out", "fee", "tax"].includes(type)) {
    return { label: "OUT", color: "text-tf-negative" };
  }
  if (type === "buy") return { label: "OUT", color: "text-tf-negative" };
  if (type === "sell") return { label: "IN", color: "text-tf-positive" };
  return { label: "-", color: "text-tf-text-tertiary" };
}

/** Format a datetime string as YYYY-MM-DD for date input. */
function toDateInputValue(isoStr: string): string {
  return isoStr.slice(0, 10);
}

interface InlineSelectProps {
  value: string;
  options: string[];
  onSave: (value: string) => void;
  testId?: string;
}

function InlineSelect({ value, options, onSave, testId }: InlineSelectProps) {
  const [editing, setEditing] = useState(false);
  const ref = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    if (editing) ref.current?.focus();
  }, [editing]);

  if (!editing) {
    const isCashFlow = CASH_FLOW_TYPES.has(value);
    return (
      <span
        onClick={() => setEditing(true)}
        className={`cursor-pointer rounded px-1 -mx-1 hover:bg-tf-bg-elevated ${isCashFlow ? "text-tf-text-primary" : "text-tf-text-tertiary"}`}
        data-testid={testId}
      >
        {value}
      </span>
    );
  }

  return (
    <select
      ref={ref}
      defaultValue={value}
      onChange={(e) => {
        const newValue = e.target.value;
        setEditing(false);
        if (newValue !== value) onSave(newValue);
      }}
      onBlur={() => setEditing(false)}
      className="bg-tf-bg-surface border border-tf-border-default rounded px-2 py-0.5 text-sm text-tf-text-primary"
      data-testid="edit-type"
    >
      {options.map((t) => (
        <option key={t} value={t}>{t}</option>
      ))}
    </select>
  );
}

interface InlineTextProps {
  value: string;
  onSave: (value: string) => void;
  type?: "text" | "number";
  align?: "left" | "right";
  placeholder?: string;
  displayValue?: string;
  testId?: string;
  editTestId?: string;
}

function InlineText({
  value,
  onSave,
  type = "text",
  align = "left",
  placeholder,
  displayValue,
  testId,
  editTestId,
}: InlineTextProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) ref.current?.focus();
  }, [editing]);

  const startEditing = () => {
    setDraft(value);
    setEditing(true);
  };

  const handleBlur = () => {
    setEditing(false);
    const trimmed = type === "text" ? draft.trim() : draft;
    if (trimmed !== value) {
      onSave(trimmed);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setEditing(false);
    } else if (e.key === "Enter") {
      ref.current?.blur();
    }
  };

  if (!editing) {
    return (
      <span
        onClick={startEditing}
        className={`cursor-pointer rounded px-1 -mx-1 hover:bg-tf-bg-elevated ${
          align === "right" ? "text-tf-text-primary" : "text-tf-text-secondary"
        } ${type === "text" ? "max-w-[150px] truncate block" : ""}`}
        data-testid={testId}
      >
        {displayValue ?? (value || "-")}
      </span>
    );
  }

  return (
    <input
      ref={ref}
      type={type}
      step={type === "number" ? "any" : undefined}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      placeholder={placeholder}
      className={`bg-tf-bg-surface border border-tf-border-default rounded px-2 py-0.5 text-sm text-tf-text-primary ${
        align === "right" ? "text-right w-28 tabular-nums" : "w-full"
      }`}
      data-testid={editTestId}
    />
  );
}

interface InlineDateProps {
  value: string;
  onSave: (value: string) => void;
  testId?: string;
  editTestId?: string;
}

function InlineDate({ value, onSave, testId, editTestId }: InlineDateProps) {
  const [editing, setEditing] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) ref.current?.focus();
  }, [editing]);

  const dateStr = toDateInputValue(value);

  const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    setEditing(false);
    const newDate = e.target.value;
    if (newDate && newDate !== dateStr && !isNaN(Date.parse(newDate))) {
      onSave(newDate + "T00:00:00Z");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") setEditing(false);
  };

  if (!editing) {
    return (
      <span
        onClick={() => setEditing(true)}
        className="cursor-pointer rounded px-1 -mx-1 hover:bg-tf-bg-elevated text-tf-text-primary"
        data-testid={testId}
      >
        {new Date(value).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        })}
      </span>
    );
  }

  return (
    <input
      ref={ref}
      type="date"
      defaultValue={dateStr}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      className="bg-tf-bg-surface border border-tf-border-default rounded px-2 py-0.5 text-sm text-tf-text-primary"
      data-testid={editTestId}
    />
  );
}

interface Props {
  accountId: string;
  activities: Activity[];
  loading: boolean;
  onActivityUpdated: (updated: Activity) => void;
  onActivityDeleted: () => void;
  onAddActivity: () => void;
}

export function ActivityTable({
  accountId,
  activities,
  loading,
  onActivityUpdated,
  onActivityDeleted,
  onAddActivity,
}: Props) {
  const [error, setError] = useState<string | null>(null);

  const saveField = async (activityId: string, update: ActivityUpdate) => {
    try {
      setError(null);
      const res = await accountsApi.updateActivity(accountId, activityId, update);
      onActivityUpdated(res.data);
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to update activity"));
    }
  };

  const handleDelete = async (activity: Activity) => {
    if (!window.confirm("Delete this activity?")) return;
    try {
      setError(null);
      await accountsApi.deleteActivity(accountId, activity.id);
      onActivityDeleted();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to delete activity"));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-24">
        <p className="text-tf-text-tertiary text-sm">Loading activities...</p>
      </div>
    );
  }

  return (
    <div>
      <div className="px-4 py-2 flex items-center justify-between bg-tf-bg-elevated/30">
        <span className="text-xs text-tf-text-tertiary">
          {activities.length} activit{activities.length === 1 ? "y" : "ies"}
        </span>
        <button
          onClick={onAddActivity}
          className="px-3 py-1 text-xs font-medium text-tf-accent-hover hover:bg-tf-accent-muted rounded transition"
          data-testid="add-activity-btn"
        >
          + Add Activity
        </button>
      </div>

      {error && (
        <div className="px-4 py-1 text-tf-negative text-xs" data-testid="inline-error">
          {error}
        </div>
      )}

      {activities.length === 0 ? (
        <div className="px-4 py-8 text-center">
          <p className="text-tf-text-tertiary text-sm">No activities found.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-tf-border-subtle bg-tf-bg-elevated/50">
                <th className="text-left px-4 py-2 font-medium text-tf-text-secondary">Date</th>
                <th className="text-left px-4 py-2 font-medium text-tf-text-secondary">Type</th>
                <th className="text-left px-4 py-2 font-medium text-tf-text-secondary">Direction</th>
                <th className="text-right px-4 py-2 font-medium text-tf-text-secondary">Amount</th>
                <th className="text-left px-4 py-2 font-medium text-tf-text-secondary">Ticker</th>
                <th className="text-left px-4 py-2 font-medium text-tf-text-secondary">Description</th>
                <th className="text-left px-4 py-2 font-medium text-tf-text-secondary">Notes</th>
                <th className="text-center px-4 py-2 font-medium text-tf-text-secondary">Status</th>
                <th className="text-right px-4 py-2 font-medium text-tf-text-secondary" />
              </tr>
            </thead>
            <tbody>
              {activities.map((activity) => {
                const dir = directionLabel(activity.type);
                const isManual = activity.provider_name === "Manual";

                return (
                  <tr
                    key={activity.id}
                    className={`border-b border-tf-border-subtle last:border-b-0 hover:bg-tf-bg-elevated/30 ${
                      !activity.is_reviewed ? "border-l-2 border-l-tf-accent-primary" : ""
                    }`}
                    data-testid={`activity-row-${activity.id}`}
                  >
                    {/* Date — editable for manual activities */}
                    <td className="px-4 py-2 text-tf-text-primary">
                      {isManual ? (
                        <InlineDate
                          value={activity.activity_date}
                          onSave={(v) => saveField(activity.id, { activity_date: v })}
                          testId={`date-cell-${activity.id}`}
                          editTestId="edit-date"
                        />
                      ) : (
                        <span data-testid={`date-cell-${activity.id}`}>
                          {new Date(activity.activity_date).toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })}
                        </span>
                      )}
                    </td>

                    {/* Type — click to edit */}
                    <td className="px-4 py-2">
                      <InlineSelect
                        value={activity.type}
                        options={ACTIVITY_TYPES}
                        onSave={(v) => saveField(activity.id, { type: v })}
                        testId={`type-cell-${activity.id}`}
                      />
                    </td>

                    <td className="px-4 py-2">
                      <span className={`text-xs font-medium ${dir.color}`}>{dir.label}</span>
                    </td>

                    {/* Amount — click to edit */}
                    <td className="px-4 py-2 text-right tabular-nums">
                      <InlineText
                        value={activity.amount ?? ""}
                        onSave={(v) => {
                          if (v !== "" && isNaN(parseFloat(v))) return;
                          saveField(activity.id, {
                            amount: v !== "" ? parseFloat(v) : undefined,
                          });
                        }}
                        type="number"
                        align="right"
                        displayValue={formatCurrency(activity.amount)}
                        testId={`amount-cell-${activity.id}`}
                        editTestId="edit-amount"
                      />
                    </td>

                    <td className="px-4 py-2 text-tf-text-secondary">
                      {activity.ticker ?? "-"}
                    </td>
                    <td className="px-4 py-2 text-tf-text-secondary max-w-[200px] truncate">
                      {activity.description ?? "-"}
                    </td>

                    {/* Notes — click to edit */}
                    <td className="px-4 py-2">
                      <InlineText
                        value={activity.notes ?? ""}
                        onSave={(v) => saveField(activity.id, { notes: v || undefined })}
                        placeholder="Notes"
                        testId={`notes-cell-${activity.id}`}
                        editTestId="edit-notes"
                      />
                    </td>

                    <td className="px-4 py-2 text-center">
                      {activity.is_reviewed ? (
                        <span className="text-tf-positive" title="Reviewed">&#10003;</span>
                      ) : (
                        <span className="text-tf-text-tertiary" title="Unreviewed">&#9711;</span>
                      )}
                      {activity.user_modified && (
                        <span
                          className="ml-1 text-tf-accent-hover text-xs"
                          title="Modified by user"
                          data-testid={`modified-indicator-${activity.id}`}
                        >
                          &#9998;
                        </span>
                      )}
                    </td>

                    {/* Actions: delete for manual activities */}
                    <td className="px-4 py-2 text-right">
                      {isManual && (
                        <button
                          onClick={() => handleDelete(activity)}
                          className="text-tf-text-tertiary hover:text-tf-negative text-xs transition"
                          title="Delete activity"
                          data-testid={`delete-btn-${activity.id}`}
                        >
                          &#10005;
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
