interface SyncButtonProps {
  onSync: () => Promise<void>;
  syncing: boolean;
}

export function SyncButton({ onSync, syncing }: SyncButtonProps) {
  const handleSync = async () => {
    if (syncing) return;
    await onSync();
  };

  return (
    <div className="flex items-center gap-4">
      <button
        onClick={handleSync}
        disabled={syncing}
        className={`px-4 py-2 rounded-md font-medium transition-colors ${
          syncing
            ? "bg-tf-bg-elevated text-tf-text-tertiary cursor-not-allowed"
            : "bg-tf-accent-primary text-tf-text-primary hover:bg-tf-accent-hover"
        }`}
      >
        {syncing ? "Syncing..." : "Sync Now"}
      </button>
    </div>
  );
}
