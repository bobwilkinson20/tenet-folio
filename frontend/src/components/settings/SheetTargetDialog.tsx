/**
 * Dialog for creating or editing a sheet target.
 */

import { useEffect, useState } from "react";
import { reportsApi } from "@/api/reports";
import { Modal } from "@/components/common/Modal";
import type { ReportSheetTarget, ReportType } from "@/types/report";
import { extractApiErrorMessage } from "@/utils/errors";

interface SheetTargetDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved: () => void;
  reportTypes: ReportType[];
  editingTarget: ReportSheetTarget | null;
}

export function SheetTargetDialog({
  isOpen,
  onClose,
  onSaved,
  reportTypes,
  editingTarget,
}: SheetTargetDialogProps) {
  const isEdit = editingTarget !== null;

  const [reportType, setReportType] = useState("");
  const [spreadsheetId, setSpreadsheetId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [configValues, setConfigValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form when dialog opens
  useEffect(() => {
    if (!isOpen) return;

    setError(null);
    setSubmitting(false);

    if (editingTarget) {
      setReportType(editingTarget.report_type);
      setSpreadsheetId(editingTarget.spreadsheet_id);
      setDisplayName(editingTarget.display_name);
      setConfigValues({ ...editingTarget.config });
    } else {
      setReportType(reportTypes.length === 1 ? reportTypes[0].id : "");
      setSpreadsheetId("");
      setDisplayName("");
      // Pre-fill defaults
      const defaults: Record<string, string> = {};
      if (reportTypes.length === 1) {
        for (const field of reportTypes[0].config_fields) {
          if (field.default) {
            defaults[field.key] = field.default;
          }
        }
      }
      setConfigValues(defaults);
    }
  }, [isOpen, editingTarget, reportTypes]);

  // Update config defaults when report type changes (create mode only)
  useEffect(() => {
    if (isEdit || !reportType) return;
    const rt = reportTypes.find((t) => t.id === reportType);
    if (!rt) return;
    const defaults: Record<string, string> = {};
    for (const field of rt.config_fields) {
      if (field.default) {
        defaults[field.key] = field.default;
      }
    }
    setConfigValues(defaults);
  }, [reportType, reportTypes, isEdit]);

  const selectedType = reportTypes.find((t) => t.id === reportType);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      if (isEdit) {
        await reportsApi.updateTarget(editingTarget.id, {
          display_name: displayName,
          config: configValues,
        });
      } else {
        await reportsApi.createTarget({
          report_type: reportType,
          spreadsheet_id: spreadsheetId,
          display_name: displayName || undefined,
          config: configValues,
        });
      }
      onSaved();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to save sheet target"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <h2 className="text-lg font-semibold text-tf-text-primary mb-4">
        {isEdit ? "Edit Sheet Target" : "Add Sheet Target"}
      </h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Report Type */}
        <div>
          <label
            htmlFor="target-report-type"
            className="block text-sm font-medium text-tf-text-secondary mb-1"
          >
            Report Type
          </label>
          {isEdit ? (
            <p className="text-sm text-tf-text-primary" data-testid="report-type-readonly">
              {selectedType?.display_name ?? reportType}
            </p>
          ) : (
            <select
              id="target-report-type"
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
              className="w-full rounded border border-tf-border-default bg-tf-bg-base px-3 py-2 text-sm text-tf-text-primary focus:border-tf-accent-primary focus:outline-none"
              required
              data-testid="report-type-select"
            >
              <option value="">Select a report type</option>
              {reportTypes.map((rt) => (
                <option key={rt.id} value={rt.id}>
                  {rt.display_name}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Spreadsheet ID */}
        <div>
          <label
            htmlFor="target-spreadsheet-id"
            className="block text-sm font-medium text-tf-text-secondary mb-1"
          >
            Spreadsheet ID
          </label>
          {isEdit ? (
            <p className="text-sm text-tf-text-primary font-mono" data-testid="spreadsheet-id-readonly">
              {spreadsheetId}
            </p>
          ) : (
            <input
              id="target-spreadsheet-id"
              type="text"
              value={spreadsheetId}
              onChange={(e) => setSpreadsheetId(e.target.value)}
              className="w-full rounded border border-tf-border-default bg-tf-bg-base px-3 py-2 text-sm text-tf-text-primary focus:border-tf-accent-primary focus:outline-none"
              placeholder="From the Google Sheets URL"
              required
              data-testid="spreadsheet-id-input"
            />
          )}
        </div>

        {/* Display Name */}
        <div>
          <label
            htmlFor="target-display-name"
            className="block text-sm font-medium text-tf-text-secondary mb-1"
          >
            Display Name
          </label>
          <input
            id="target-display-name"
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full rounded border border-tf-border-default bg-tf-bg-base px-3 py-2 text-sm text-tf-text-primary focus:border-tf-accent-primary focus:outline-none"
            placeholder={isEdit ? "" : "Will default to sheet name"}
            data-testid="display-name-input"
          />
        </div>

        {/* Dynamic config fields */}
        {selectedType?.config_fields.map((field) => (
          <div key={field.key}>
            <label
              htmlFor={`target-config-${field.key}`}
              className="block text-sm font-medium text-tf-text-secondary mb-1"
            >
              {field.label}
            </label>
            <input
              id={`target-config-${field.key}`}
              type="text"
              value={configValues[field.key] ?? ""}
              onChange={(e) =>
                setConfigValues((prev) => ({
                  ...prev,
                  [field.key]: e.target.value,
                }))
              }
              className="w-full rounded border border-tf-border-default bg-tf-bg-base px-3 py-2 text-sm text-tf-text-primary focus:border-tf-accent-primary focus:outline-none"
              required={field.required}
              data-testid={`config-field-${field.key}`}
            />
            {field.help_text && (
              <p className="mt-1 text-xs text-tf-text-tertiary">
                {field.help_text}
              </p>
            )}
          </div>
        ))}

        {error && (
          <p className="text-sm text-tf-negative" data-testid="target-error">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-tf-border-default px-4 py-2 text-sm font-medium text-tf-text-secondary hover:bg-tf-bg-elevated"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded bg-tf-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-tf-accent-primary/90 disabled:opacity-50"
          >
            {submitting ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
