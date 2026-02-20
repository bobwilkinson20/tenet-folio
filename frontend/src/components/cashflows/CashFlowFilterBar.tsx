interface Props {
  unreviewedOnly: boolean;
  onUnreviewedOnlyChange: (value: boolean) => void;
  hideInactive: boolean;
  onHideInactiveChange: (value: boolean) => void;
  hideZeroNet: boolean;
  onHideZeroNetChange: (value: boolean) => void;
  startDate: string;
  endDate: string;
  onStartDateChange: (value: string) => void;
  onEndDateChange: (value: string) => void;
}

export function CashFlowFilterBar({
  unreviewedOnly,
  onUnreviewedOnlyChange,
  hideInactive,
  onHideInactiveChange,
  hideZeroNet,
  onHideZeroNetChange,
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
}: Props) {
  const toggleClass = (active: boolean) =>
    `rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
      active
        ? "border border-tf-accent-border bg-tf-accent-muted text-tf-accent-hover"
        : "border border-tf-border-subtle text-tf-text-secondary hover:bg-tf-bg-elevated"
    }`;

  return (
    <div className="flex flex-wrap items-center gap-4">
      <button
        onClick={() => onUnreviewedOnlyChange(!unreviewedOnly)}
        className={toggleClass(unreviewedOnly)}
        data-testid="unreviewed-toggle"
      >
        Unreviewed only
      </button>

      <button
        onClick={() => onHideInactiveChange(!hideInactive)}
        className={toggleClass(hideInactive)}
        data-testid="hide-inactive-toggle"
      >
        Hide inactive
      </button>

      <button
        onClick={() => onHideZeroNetChange(!hideZeroNet)}
        className={toggleClass(hideZeroNet)}
        data-testid="hide-zero-net-toggle"
      >
        Hide net $0
      </button>

      <div className="flex items-center gap-2">
        <label className="text-sm text-tf-text-tertiary">From</label>
        <input
          type="date"
          value={startDate}
          onChange={(e) => onStartDateChange(e.target.value)}
          className="bg-tf-bg-elevated border border-tf-border-subtle rounded-lg px-3 py-1.5 text-sm text-tf-text-primary"
          data-testid="start-date"
        />
      </div>

      <div className="flex items-center gap-2">
        <label className="text-sm text-tf-text-tertiary">To</label>
        <input
          type="date"
          value={endDate}
          onChange={(e) => onEndDateChange(e.target.value)}
          className="bg-tf-bg-elevated border border-tf-border-subtle rounded-lg px-3 py-1.5 text-sm text-tf-text-primary"
          data-testid="end-date"
        />
      </div>
    </div>
  );
}
