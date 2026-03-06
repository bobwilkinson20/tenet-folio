/**
 * Reports settings panel — Google Sheets credentials and sheet targets.
 */

import { useEffect, useState } from "react";
import { reportsApi } from "@/api/reports";
import type {
  GoogleSheetsCredentialStatus,
  ReportSheetTarget,
  ReportType,
} from "@/types/report";
import { extractApiErrorMessage } from "@/utils/errors";
import { SheetTargetDialog } from "./SheetTargetDialog";

export function ReportsSettings() {
  const [credentialStatus, setCredentialStatus] =
    useState<GoogleSheetsCredentialStatus | null>(null);
  const [targets, setTargets] = useState<ReportSheetTarget[]>([]);
  const [reportTypes, setReportTypes] = useState<ReportType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Credential configuration
  const [showCredentialForm, setShowCredentialForm] = useState(false);
  const [credentialJson, setCredentialJson] = useState("");
  const [submittingCredential, setSubmittingCredential] = useState(false);
  const [credentialError, setCredentialError] = useState<string | null>(null);

  // Sheet target dialog
  const [showTargetDialog, setShowTargetDialog] = useState(false);
  const [editingTarget, setEditingTarget] = useState<ReportSheetTarget | null>(
    null,
  );

  // Delete confirmation
  const [deletingTargetId, setDeletingTargetId] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [credRes, targetsRes, typesRes] = await Promise.all([
        reportsApi.getCredentialStatus(),
        reportsApi.getTargets(),
        reportsApi.getReportTypes(),
      ]);
      setCredentialStatus(credRes.data);
      setTargets(targetsRes.data);
      setReportTypes(typesRes.data);
      setError(null);
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to load report settings"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleSetCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    setCredentialError(null);
    setSubmittingCredential(true);

    try {
      const response = await reportsApi.setCredentials(credentialJson);
      setCredentialStatus(response.data);
      setShowCredentialForm(false);
      setCredentialJson("");
      // Refresh targets in case they depend on credentials
      const targetsRes = await reportsApi.getTargets();
      setTargets(targetsRes.data);
    } catch (err) {
      setCredentialError(
        extractApiErrorMessage(err, "Failed to save credentials"),
      );
    } finally {
      setSubmittingCredential(false);
    }
  };

  const handleRemoveCredentials = async () => {
    try {
      await reportsApi.removeCredentials();
      setCredentialStatus({ configured: false, service_account_email: null });
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to remove credentials"));
    }
  };

  const handleDeleteTarget = async (targetId: string) => {
    try {
      await reportsApi.deleteTarget(targetId);
      setTargets((prev) => prev.filter((t) => t.id !== targetId));
      setDeletingTargetId(null);
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to delete target"));
    }
  };

  const handleTargetSaved = () => {
    setShowTargetDialog(false);
    setEditingTarget(null);
    fetchData();
  };

  const reportTypeLabel = (id: string) => {
    const rt = reportTypes.find((t) => t.id === id);
    return rt?.display_name ?? id;
  };

  if (loading) {
    return <p className="text-tf-text-tertiary">Loading report settings...</p>;
  }

  if (error && !credentialStatus) {
    return <p className="text-sm text-tf-negative">{error}</p>;
  }

  return (
    <div className="space-y-8">
      {/* Google Sheets Credentials */}
      <section>
        <h2 className="text-lg font-semibold text-tf-text-primary mb-4">
          Google Sheets Credentials
        </h2>

        {credentialStatus?.configured ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center rounded-full bg-tf-positive/10 px-2.5 py-0.5 text-xs font-medium text-tf-positive">
                Configured
              </span>
              {credentialStatus.service_account_email && (
                <span
                  className="text-sm text-tf-text-secondary"
                  data-testid="service-account-email"
                >
                  {credentialStatus.service_account_email}
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setShowCredentialForm(true);
                  setCredentialError(null);
                }}
                className="rounded border border-tf-border-default px-3 py-1.5 text-sm font-medium text-tf-text-secondary hover:bg-tf-bg-elevated"
              >
                Reconfigure
              </button>
              <button
                onClick={handleRemoveCredentials}
                className="rounded border border-tf-border-default px-3 py-1.5 text-sm font-medium text-tf-negative hover:bg-tf-negative/10"
              >
                Remove
              </button>
            </div>
          </div>
        ) : (
          <div>
            <p className="text-sm text-tf-text-tertiary mb-3">
              Paste your Google service account JSON key to enable report export.
            </p>
            <button
              onClick={() => {
                setShowCredentialForm(true);
                setCredentialError(null);
              }}
              className="rounded bg-tf-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-tf-accent-primary/90"
              data-testid="configure-credentials-btn"
            >
              Configure
            </button>
          </div>
        )}

        {/* Credential form */}
        {showCredentialForm && (
          <form onSubmit={handleSetCredentials} className="mt-4 space-y-3">
            <label
              htmlFor="credentials-json"
              className="block text-sm font-medium text-tf-text-secondary"
            >
              Service Account JSON
            </label>
            <textarea
              id="credentials-json"
              value={credentialJson}
              onChange={(e) => setCredentialJson(e.target.value)}
              className="w-full rounded border border-tf-border-default bg-tf-bg-base px-3 py-2 text-sm text-tf-text-primary font-mono focus:border-tf-accent-primary focus:outline-none"
              rows={8}
              placeholder='{"type": "service_account", "client_email": "...", ...}'
              required
              data-testid="credentials-json-input"
            />
            {credentialError && (
              <p className="text-sm text-tf-negative" data-testid="credential-error">
                {credentialError}
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={submittingCredential}
                className="rounded bg-tf-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-tf-accent-primary/90 disabled:opacity-50"
              >
                {submittingCredential ? "Validating..." : "Save"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowCredentialForm(false);
                  setCredentialJson("");
                  setCredentialError(null);
                }}
                className="rounded border border-tf-border-default px-4 py-2 text-sm font-medium text-tf-text-secondary hover:bg-tf-bg-elevated"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </section>

      {/* Sheet Targets — only shown when credentials are configured */}
      {credentialStatus?.configured && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-tf-text-primary">
              Sheet Targets
            </h2>
            <button
              onClick={() => {
                setEditingTarget(null);
                setShowTargetDialog(true);
              }}
              className="rounded bg-tf-accent-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-tf-accent-primary/90"
              data-testid="add-target-btn"
            >
              Add Sheet Target
            </button>
          </div>

          {error && (
            <p className="text-sm text-tf-negative mb-3">{error}</p>
          )}

          {targets.length === 0 ? (
            <p className="text-sm text-tf-text-tertiary">
              No sheet targets configured. Add one to start exporting reports.
            </p>
          ) : (
            <div className="space-y-2">
              {targets.map((target) => (
                <div
                  key={target.id}
                  className="flex items-center justify-between rounded border border-tf-border-default p-3"
                  data-testid={`target-row-${target.id}`}
                >
                  <div>
                    <p className="text-sm font-medium text-tf-text-primary">
                      {target.display_name}
                    </p>
                    <p className="text-xs text-tf-text-tertiary">
                      {reportTypeLabel(target.report_type)} &middot;{" "}
                      {target.spreadsheet_id}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        setEditingTarget(target);
                        setShowTargetDialog(true);
                      }}
                      className="rounded border border-tf-border-default px-2.5 py-1 text-xs font-medium text-tf-text-secondary hover:bg-tf-bg-elevated"
                    >
                      Edit
                    </button>
                    {deletingTargetId === target.id ? (
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleDeleteTarget(target.id)}
                          className="rounded bg-tf-negative px-2.5 py-1 text-xs font-medium text-white hover:bg-tf-negative/90"
                          data-testid="confirm-delete-btn"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => setDeletingTargetId(null)}
                          className="rounded border border-tf-border-default px-2.5 py-1 text-xs font-medium text-tf-text-secondary hover:bg-tf-bg-elevated"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setDeletingTargetId(target.id)}
                        className="rounded border border-tf-border-default px-2.5 py-1 text-xs font-medium text-tf-negative hover:bg-tf-negative/10"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Sheet Target Dialog */}
          <SheetTargetDialog
            isOpen={showTargetDialog}
            onClose={() => {
              setShowTargetDialog(false);
              setEditingTarget(null);
            }}
            onSaved={handleTargetSaved}
            reportTypes={reportTypes}
            editingTarget={editingTarget}
          />
        </section>
      )}
    </div>
  );
}
