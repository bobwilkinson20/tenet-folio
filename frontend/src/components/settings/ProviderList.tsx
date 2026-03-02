/**
 * Component to list and manage data providers (enable/disable toggle).
 */

import { useEffect, useState } from "react";
import { providersApi } from "@/api";
import type { ProviderStatus } from "@/types/provider";
import { extractApiErrorMessage } from "@/utils/errors";
import { PlaidItemList } from "./PlaidItemList";
import { ProviderSetupDialog } from "./ProviderSetupDialog";

const PROVIDER_DESCRIPTIONS: Record<string, string> = {
  SnapTrade: "Brokerage aggregator supporting many institutions",
  SimpleFIN: "Bank and investment account aggregator",
  IBKR: "Interactive Brokers via Flex Web Service",
  Coinbase: "Cryptocurrency exchange via Advanced Trade API",
  Schwab: "Charles Schwab brokerage accounts",
  Plaid: "Bank and investment aggregator via Plaid Link",
};

function formatSyncTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleString();
}

export function ProviderList() {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [togglingProvider, setTogglingProvider] = useState<string | null>(null);
  const [setupProvider, setSetupProvider] = useState<string | null>(null);

  const fetchProviders = async () => {
    try {
      setLoading(true);
      const response = await providersApi.list();
      setProviders(response.data);
      setError(null);
    } catch {
      setError("Failed to load providers");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProviders();
  }, []);

  const handleToggle = async (provider: ProviderStatus) => {
    const newEnabled = !provider.is_enabled;
    setTogglingProvider(provider.name);

    // Optimistic update
    setProviders((prev) =>
      prev.map((p) =>
        p.name === provider.name ? { ...p, is_enabled: newEnabled } : p,
      ),
    );

    try {
      const response = await providersApi.update(provider.name, newEnabled);
      // Replace with server response
      setProviders((prev) =>
        prev.map((p) => (p.name === provider.name ? response.data : p)),
      );
    } catch {
      // Rollback on error
      setProviders((prev) =>
        prev.map((p) =>
          p.name === provider.name ? { ...p, is_enabled: !newEnabled } : p,
        ),
      );
    } finally {
      setTogglingProvider(null);
    }
  };

  const handleRemoveCredentials = async (providerName: string) => {
    if (!window.confirm(`Remove credentials for ${providerName}?`)) return;

    try {
      await providersApi.removeCredentials(providerName);
      await fetchProviders();
    } catch (err) {
      await fetchProviders();
      setError(extractApiErrorMessage(err, "Failed to remove credentials"));
    }
  };

  if (loading) {
    return <div className="text-tf-text-tertiary">Loading providers...</div>;
  }

  if (error) {
    return <div className="text-tf-negative">{error}</div>;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-tf-text-secondary">
        Manage which data providers are active during sync. Configure providers
        below or via your <code>.env</code> file.
      </p>

      <div className="space-y-3">
        {providers.map((provider) => (
          <div
            key={provider.name}
            className="flex items-start gap-4 rounded-lg border border-tf-border-default p-4"
          >
            <label className="relative mt-1 inline-flex cursor-pointer items-center shrink-0">
              <input
                type="checkbox"
                checked={provider.is_enabled}
                disabled={!provider.has_credentials || togglingProvider === provider.name}
                onChange={() => handleToggle(provider)}
                className="peer sr-only"
                aria-label={`${provider.is_enabled ? "Disable" : "Enable"} ${provider.name}`}
              />
              <div
                className={`h-6 w-11 rounded-full after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-tf-border-default after:bg-tf-text-primary after:transition-all after:content-[''] peer-checked:after:translate-x-full peer-checked:after:border-tf-text-primary ${
                  !provider.has_credentials
                    ? "cursor-not-allowed bg-tf-bg-elevated"
                    : provider.is_enabled
                      ? "bg-tf-accent-primary"
                      : "bg-tf-bg-elevated"
                }`}
              />
            </label>

            <div className="flex-1">
              <div className="flex items-center gap-3">
                <h3 className="font-medium text-tf-text-primary">{provider.name}</h3>
                {provider.has_credentials ? (
                  <span className="inline-flex items-center rounded-full bg-tf-positive/10 px-2 py-0.5 text-xs font-medium text-tf-positive">
                    Configured
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded-full bg-tf-bg-elevated px-2 py-0.5 text-xs font-medium text-tf-text-tertiary">
                    Not Configured
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-tf-text-tertiary">
                {PROVIDER_DESCRIPTIONS[provider.name] ?? "Data provider"}
              </p>
              <div className="mt-1 flex gap-4 text-xs text-tf-text-tertiary">
                {provider.account_count > 0 && (
                  <span>
                    {provider.account_count}{" "}
                    {provider.account_count === 1 ? "account" : "accounts"}
                  </span>
                )}
                {provider.last_sync_time && (
                  <span>
                    Last sync: {formatSyncTime(provider.last_sync_time)}
                  </span>
                )}
              </div>
              {provider.supports_setup && (
                <div className="mt-2 flex gap-2">
                  {provider.has_credentials ? (
                    <>
                      <button
                        onClick={() => setSetupProvider(provider.name)}
                        className="rounded border border-tf-border-default px-3 py-1 text-xs font-medium text-tf-text-secondary hover:bg-tf-bg-elevated"
                      >
                        Reconfigure
                      </button>
                      <button
                        onClick={() => handleRemoveCredentials(provider.name)}
                        className="rounded border border-tf-negative/30 px-3 py-1 text-xs font-medium text-tf-negative hover:bg-tf-negative/10"
                      >
                        Remove
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setSetupProvider(provider.name)}
                      className="rounded bg-tf-accent-primary px-3 py-1 text-xs font-medium text-white hover:bg-tf-accent-primary/90"
                    >
                      Configure
                    </button>
                  )}
                </div>
              )}
              {provider.name === "Plaid" && provider.has_credentials && (
                <PlaidItemList />
              )}
            </div>
          </div>
        ))}
      </div>

      {setupProvider && (
        <ProviderSetupDialog
          providerName={setupProvider}
          isOpen={true}
          onClose={() => setSetupProvider(null)}
          onSuccess={() => fetchProviders()}
        />
      )}
    </div>
  );
}
