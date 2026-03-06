interface ReportButtonProps {
  onClick: () => void;
}

export function ReportButton({ onClick }: ReportButtonProps) {
  return (
    <button
      onClick={onClick}
      className="px-4 py-2 rounded-md font-medium transition-colors bg-tf-bg-elevated text-tf-text-secondary hover:text-tf-text-primary hover:bg-tf-border-subtle"
    >
      Report
    </button>
  );
}
