/**
 * Dialog for generating reports — handles target selection and result display.
 */

import { useEffect, useMemo, useState } from "react";
import { reportsApi } from "@/api/reports";
import type { GoogleSheetsReportResponse } from "@/api/reports";
import { Modal } from "@/components/common/Modal";
import type { ReportSheetTarget, ReportType } from "@/types/report";
import { extractApiErrorMessage } from "@/utils/errors";

interface ReportGenerationDialogProps {
  isOpen: boolean;
  onClose: () => void;
  allocationOnly: boolean;
}

export function ReportGenerationDialog({
  isOpen,
  onClose,
  allocationOnly,
}: ReportGenerationDialogProps) {
  const [reportTypes, setReportTypes] = useState<ReportType[]>([]);
  const [targets, setTargets] = useState<ReportSheetTarget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedTypeId, setSelectedTypeId] = useState("");
  const [selectedTargetId, setSelectedTargetId] = useState("");

  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GoogleSheetsReportResponse | null>(null);

  // Fetch data when dialog opens
  useEffect(() => {
    if (!isOpen) return;

    setError(null);
    setResult(null);
    setGenerating(false);
    setLoading(true);

    Promise.all([reportsApi.getReportTypes(), reportsApi.getTargets()])
      .then(([typesRes, targetsRes]) => {
        const types = typesRes.data;
        const allTargets = targetsRes.data;
        setReportTypes(types);
        setTargets(allTargets);

        // Auto-select if only one type
        if (types.length === 1) {
          setSelectedTypeId(types[0].id);
          // Auto-select if only one target for this type
          const typeTargets = allTargets.filter(
            (t) => t.report_type === types[0].id,
          );
          if (typeTargets.length === 1) {
            setSelectedTargetId(typeTargets[0].id);
          } else {
            setSelectedTargetId("");
          }
        } else {
          setSelectedTypeId("");
          setSelectedTargetId("");
        }
      })
      .catch((err) => {
        setError(extractApiErrorMessage(err, "Failed to load report options"));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [isOpen]);

  const filteredTargets = useMemo(
    () => targets.filter((t) => t.report_type === selectedTypeId),
    [targets, selectedTypeId],
  );

  // Auto-select target when type changes
  useEffect(() => {
    if (filteredTargets.length === 1) {
      setSelectedTargetId(filteredTargets[0].id);
    } else if (
      selectedTargetId &&
      !filteredTargets.some((t) => t.id === selectedTargetId)
    ) {
      setSelectedTargetId("");
    }
  }, [selectedTypeId, filteredTargets, selectedTargetId]);

  const handleGenerate = async () => {
    if (!selectedTargetId) return;

    setGenerating(true);
    setError(null);
    setResult(null);

    try {
      const response = await reportsApi.generateGoogleSheets({
        target_id: selectedTargetId,
        allocation_only: allocationOnly,
      });
      setResult(response.data);
    } catch (err) {
      setError(extractApiErrorMessage(err, "Report generation failed"));
    } finally {
      setGenerating(false);
    }
  };

  const selectedTarget = targets.find((t) => t.id === selectedTargetId);

  return (
    <Modal isOpen={isOpen} onClose={generating ? undefined : onClose}>
      <h2 className="text-lg font-semibold text-tf-text-primary mb-4">
        Generate Report
      </h2>

      {loading ? (
        <p className="text-tf-text-tertiary py-4" data-testid="report-dialog-loading">
          Loading report options...
        </p>
      ) : result ? (
        /* Success result */
        <div data-testid="report-dialog-success">
          <p className="text-tf-text-primary">
            Created tab{" "}
            <span className="font-semibold">{result.tab_name}</span> with{" "}
            {result.rows_written} row{result.rows_written !== 1 ? "s" : ""}.
          </p>
          <div className="flex justify-end pt-4">
            <button
              onClick={onClose}
              className="rounded bg-tf-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-tf-accent-primary/90"
            >
              Done
            </button>
          </div>
        </div>
      ) : (
        /* Selection + Generate form */
        <div className="space-y-4">
          {/* Report Type selector — only if multiple types */}
          {reportTypes.length > 1 && (
            <div>
              <label
                htmlFor="report-type"
                className="block text-sm font-medium text-tf-text-secondary mb-1"
              >
                Report Type
              </label>
              <select
                id="report-type"
                value={selectedTypeId}
                onChange={(e) => setSelectedTypeId(e.target.value)}
                className="w-full rounded border border-tf-border-default bg-tf-bg-base px-3 py-2 text-sm text-tf-text-primary focus:border-tf-accent-primary focus:outline-none"
                data-testid="report-type-select"
              >
                <option value="">Select a report type</option>
                {reportTypes.map((rt) => (
                  <option key={rt.id} value={rt.id}>
                    {rt.display_name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Target selector — shown when type is selected */}
          {selectedTypeId && filteredTargets.length > 1 && (
            <div>
              <label
                htmlFor="report-target"
                className="block text-sm font-medium text-tf-text-secondary mb-1"
              >
                Sheet Target
              </label>
              <select
                id="report-target"
                value={selectedTargetId}
                onChange={(e) => setSelectedTargetId(e.target.value)}
                className="w-full rounded border border-tf-border-default bg-tf-bg-base px-3 py-2 text-sm text-tf-text-primary focus:border-tf-accent-primary focus:outline-none"
                data-testid="report-target-select"
              >
                <option value="">Select a target</option>
                {filteredTargets.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.display_name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Auto-selected target display */}
          {selectedTypeId &&
            filteredTargets.length === 1 &&
            selectedTarget && (
              <p className="text-sm text-tf-text-secondary" data-testid="auto-selected-target">
                Target: <span className="font-medium">{selectedTarget.display_name}</span>
              </p>
            )}

          {/* No targets message */}
          {selectedTypeId && filteredTargets.length === 0 && (
            <p className="text-sm text-tf-text-tertiary" data-testid="no-targets-message">
              No sheet targets configured for this report type. Add one in{" "}
              <a
                href="/settings?tab=reports"
                className="text-tf-accent-primary hover:underline"
              >
                Settings &gt; Reports
              </a>
              .
            </p>
          )}

          {error && (
            <div
              className="bg-tf-negative/10 border border-tf-negative/20 rounded-md p-3"
              data-testid="report-dialog-error"
            >
              <p className="text-sm text-tf-negative">{error}</p>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={generating}
              className="rounded border border-tf-border-default px-4 py-2 text-sm font-medium text-tf-text-secondary hover:bg-tf-bg-elevated disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={!selectedTargetId || generating}
              className="rounded bg-tf-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-tf-accent-primary/90 disabled:opacity-50"
              data-testid="generate-btn"
            >
              {generating ? "Generating..." : "Generate"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
