interface Props {
  enabled: boolean;
  onChange: (value: boolean) => void;
}

export function AllocationFilterToggle({ enabled, onChange }: Props) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <div className="relative">
        <input
          type="checkbox"
          className="sr-only"
          checked={enabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <div
          className={`w-9 h-5 rounded-full transition-colors ${
            enabled ? "bg-tf-accent-primary" : "bg-tf-bg-elevated"
          }`}
        />
        <div
          className={`absolute top-0.5 left-0.5 w-4 h-4 bg-tf-text-primary rounded-full transition-transform ${
            enabled ? "translate-x-4" : ""
          }`}
        />
      </div>
      <span className="text-sm text-tf-text-secondary">Allocation accounts only</span>
    </label>
  );
}
