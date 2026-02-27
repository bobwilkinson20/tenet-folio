interface ReportButtonProps {
  onReport: () => Promise<void>;
  generating: boolean;
}

export function ReportButton({ onReport, generating }: ReportButtonProps) {
  const handleReport = async () => {
    if (generating) return;
    await onReport();
  };

  return (
    <button
      onClick={handleReport}
      disabled={generating}
      className={`px-4 py-2 rounded-md font-medium transition-colors ${
        generating
          ? "bg-tf-bg-elevated text-tf-text-tertiary cursor-not-allowed"
          : "bg-tf-bg-elevated text-tf-text-secondary hover:text-tf-text-primary hover:bg-tf-border-subtle"
      }`}
    >
      {generating ? "Generating..." : "Report"}
    </button>
  );
}
