import type { GoogleSheetsReportResponse } from "../../api/reports";

interface ReportResultModalProps {
  isOpen: boolean;
  onClose: () => void;
  generating: boolean;
  result: GoogleSheetsReportResponse | null;
  errorMessage: string | null;
}

export function ReportResultModal({
  isOpen,
  onClose,
  generating,
  result,
  errorMessage,
}: ReportResultModalProps) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      data-testid="report-result-modal"
    >
      <div className="bg-tf-bg-surface border border-tf-border-default rounded-lg w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-tf-border-subtle">
          <h2 className="text-lg font-semibold text-tf-text-primary">
            Report
          </h2>
          <button
            onClick={onClose}
            className="text-tf-text-tertiary hover:text-tf-text-secondary"
            data-testid="report-result-close"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4">
          {generating ? (
            <div
              className="flex items-center justify-center py-8"
              data-testid="report-loading"
            >
              <svg
                className="animate-spin h-6 w-6 text-tf-accent-primary mr-3"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span className="text-tf-text-secondary">
                Generating report...
              </span>
            </div>
          ) : errorMessage ? (
            <div
              className="bg-tf-negative/10 border border-tf-negative/20 rounded-md p-4"
              data-testid="report-error"
            >
              <p className="text-sm text-tf-negative">{errorMessage}</p>
            </div>
          ) : result ? (
            <div data-testid="report-success">
              <p className="text-tf-text-primary">
                Created tab{" "}
                <span className="font-semibold">{result.tab_name}</span> with{" "}
                {result.rows_written} row{result.rows_written !== 1 ? "s" : ""}.
              </p>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        {!generating && (
          <div className="px-6 py-3 border-t border-tf-border-subtle flex justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-tf-bg-elevated text-tf-text-secondary rounded-md hover:text-tf-text-primary text-sm font-medium"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
