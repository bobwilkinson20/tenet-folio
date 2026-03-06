import { useCallback, useEffect, useRef, useState } from "react";
import { snaptradeApi } from "@/api/snaptrade";
import type { SnapTradeConnection } from "@/api/snaptrade";

export function SnapTradeConnectionList() {
  const [connections, setConnections] = useState<SnapTradeConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const oauthPending = useRef(false);

  const fetchConnections = useCallback(async () => {
    try {
      setLoading(true);
      setFetchError(false);
      const response = await snaptradeApi.listConnections();
      setConnections(response.data);
    } catch {
      setFetchError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  // Auto-refresh when user returns from brokerage OAuth tab
  useEffect(() => {
    const handleFocus = () => {
      if (oauthPending.current) {
        oauthPending.current = false;
        fetchConnections();
      }
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [fetchConnections]);

  const handleAddConnection = async () => {
    setActionError(null);
    setConnecting(true);
    // Open window synchronously to avoid popup blocker (Safari)
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) {
      setActionError("Popup blocked. Please allow popups for this page and try again.");
      setConnecting(false);
      return;
    }
    try {
      const response = await snaptradeApi.getConnectUrl();
      authWindow.location.href = response.data.redirect_url;
      oauthPending.current = true;
    } catch {
      authWindow.close();
      setActionError("Failed to generate connection URL.");
    } finally {
      setConnecting(false);
    }
  };

  const handleRemove = async (
    authorizationId: string,
    connectionName: string,
  ) => {
    const confirmed = window.confirm(
      `Remove ${connectionName}? This will disconnect the brokerage and you'll need to re-connect to sync again.`,
    );
    if (!confirmed) return;

    setRemovingId(authorizationId);
    setActionError(null);
    try {
      await snaptradeApi.removeConnection(authorizationId);
      setConnections((prev) =>
        prev.filter((c) => c.authorization_id !== authorizationId),
      );
    } catch {
      setActionError("Failed to remove connection. Please try again.");
    } finally {
      setRemovingId(null);
    }
  };

  const handleRefresh = async (authorizationId: string) => {
    setRefreshingId(authorizationId);
    setActionError(null);
    // Open window synchronously to avoid popup blocker (Safari)
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) {
      setActionError("Popup blocked. Please allow popups for this page and try again.");
      setRefreshingId(null);
      return;
    }
    try {
      const response =
        await snaptradeApi.refreshConnection(authorizationId);
      authWindow.location.href = response.data.redirect_url;
      oauthPending.current = true;
    } catch {
      authWindow.close();
      setActionError("Failed to generate reconnect URL. Please try again.");
    } finally {
      setRefreshingId(null);
    }
  };

  return (
    <div className="mt-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-tf-text-secondary">
          Brokerage Connections
        </span>
        <button
          onClick={handleAddConnection}
          disabled={connecting}
          className="rounded bg-tf-accent-primary px-3 py-1 text-xs font-medium text-white hover:bg-tf-accent-primary/90 disabled:opacity-50"
        >
          {connecting ? "Connecting..." : "Add Connection"}
        </button>
      </div>

      {actionError && (
        <p className="text-xs text-tf-negative">{actionError}</p>
      )}

      {fetchError ? (
        <p className="text-xs text-tf-negative">
          Failed to load brokerage connections.
        </p>
      ) : loading && connections.length === 0 ? (
        <p className="text-xs text-tf-text-tertiary">Loading...</p>
      ) : connections.length === 0 ? (
        <p className="text-xs text-tf-text-tertiary">
          No brokerage connections yet. Click "Add Connection" to get started.
        </p>
      ) : (
        <ul className="space-y-2">
          {connections.map((conn) => (
            <li
              key={conn.authorization_id}
              className="flex items-center justify-between rounded border border-tf-border-default px-3 py-2 text-sm"
            >
              <div className="flex flex-col">
                <span className="text-tf-text-primary">
                  {conn.name || conn.brokerage_name}
                </span>
                {conn.brokerage_name !== conn.name && (
                  <span className="text-xs text-tf-text-tertiary">
                    {conn.brokerage_name}
                  </span>
                )}
                {conn.disabled && (
                  <span className="text-xs text-tf-negative">
                    {conn.error_message || "Connection disabled"}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleRefresh(conn.authorization_id)}
                  disabled={refreshingId === conn.authorization_id}
                  aria-label={`Update ${conn.name || conn.brokerage_name}`}
                  className="rounded border border-tf-border-default px-2 py-1 text-xs text-tf-text-secondary hover:bg-tf-bg-elevated disabled:opacity-50"
                >
                  {refreshingId === conn.authorization_id
                    ? "Updating..."
                    : "Update"}
                </button>
                <button
                  onClick={() =>
                    handleRemove(
                      conn.authorization_id,
                      conn.name || conn.brokerage_name,
                    )
                  }
                  disabled={removingId === conn.authorization_id}
                  aria-label={`Remove ${conn.name || conn.brokerage_name}`}
                  className="text-xs text-tf-negative hover:underline disabled:opacity-50"
                >
                  {removingId === conn.authorization_id
                    ? "Removing..."
                    : "Remove"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
