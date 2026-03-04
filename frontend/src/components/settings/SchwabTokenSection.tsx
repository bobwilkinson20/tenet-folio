import { useCallback, useEffect, useState } from "react";
import { schwabApi } from "@/api/schwab";
import type { SchwabTokenStatus } from "@/api/schwab";

export function SchwabTokenSection() {
  const [tokenStatus, setTokenStatus] = useState<SchwabTokenStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [authState, setAuthState] = useState<string | null>(null);
  const [showPasteFlow, setShowPasteFlow] = useState(false);
  const [redirectUrl, setRedirectUrl] = useState("");
  const [exchanging, setExchanging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      setLoading(true);
      const response = await schwabApi.getTokenStatus();
      setTokenStatus(response.data);
    } catch {
      // Silently fail — component just won't render
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Poll token status while the paste flow is visible (callback may complete it)
  useEffect(() => {
    if (!showPasteFlow) return;

    const interval = setInterval(async () => {
      try {
        const response = await schwabApi.getTokenStatus();
        if (response.data.status === "valid") {
          setShowPasteFlow(false);
          setRedirectUrl("");
          setAuthState(null);
          setSuccess("Schwab authorized successfully via callback.");
          setTokenStatus(response.data);
        }
      } catch {
        // Ignore polling errors
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [showPasteFlow]);

  const handleAuthorize = async () => {
    setError(null);
    setSuccess(null);
    // Open the window synchronously so Safari doesn't block it as a popup.
    // We'll navigate it to the auth URL once the API call resolves.
    const authWindow = window.open("about:blank", "_blank");
    try {
      const response = await schwabApi.createAuthUrl();
      setAuthState(response.data.state);
      setShowPasteFlow(true);
      if (authWindow) {
        authWindow.location.href = response.data.authorization_url;
      }
    } catch {
      if (authWindow) authWindow.close();
      setError("Failed to generate authorization URL.");
    }
  };

  const handleExchange = async () => {
    if (!authState || !redirectUrl.trim()) return;
    setExchanging(true);
    setError(null);
    try {
      const response = await schwabApi.exchangeToken(authState, redirectUrl.trim());
      setSuccess(response.data.message);
      setShowPasteFlow(false);
      setRedirectUrl("");
      setAuthState(null);
      await fetchStatus();
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || "Token exchange failed.");
    } finally {
      setExchanging(false);
    }
  };

  const handleCancel = () => {
    setShowPasteFlow(false);
    setRedirectUrl("");
    setAuthState(null);
    setError(null);
  };

  if (loading || !tokenStatus || tokenStatus.status === "no_credentials") {
    return null;
  }

  const statusBadge = () => {
    switch (tokenStatus.status) {
      case "valid":
        return (
          <span className="inline-flex items-center rounded-full bg-tf-positive/10 px-2 py-0.5 text-xs font-medium text-tf-positive">
            Token Valid
          </span>
        );
      case "expiring_soon":
        return (
          <span className="inline-flex items-center rounded-full bg-tf-warning/10 px-2 py-0.5 text-xs font-medium text-tf-warning">
            Expiring Soon
          </span>
        );
      case "expired":
        return (
          <span className="inline-flex items-center rounded-full bg-tf-negative/10 px-2 py-0.5 text-xs font-medium text-tf-negative">
            Token Expired
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center rounded-full bg-tf-bg-elevated px-2 py-0.5 text-xs font-medium text-tf-text-tertiary">
            Not Authorized
          </span>
        );
    }
  };

  const isExpiring = tokenStatus.status === "expiring_soon" || tokenStatus.status === "expired";
  const needsAuth = tokenStatus.status === "no_token" || tokenStatus.status === "expired";

  return (
    <div className="mt-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-tf-text-secondary">
            OAuth Token
          </span>
          {statusBadge()}
        </div>
        {!showPasteFlow && (
          <button
            onClick={handleAuthorize}
            className={`rounded px-3 py-1 text-xs font-medium ${
              needsAuth
                ? "bg-tf-accent-primary text-white hover:bg-tf-accent-primary/90"
                : "border border-tf-border-default text-tf-text-secondary hover:bg-tf-bg-elevated"
            }`}
          >
            {needsAuth ? "Authorize" : "Re-authorize"}
          </button>
        )}
      </div>

      {tokenStatus.status === "valid" && tokenStatus.days_remaining !== null && (
        <p className="text-xs text-tf-text-tertiary">
          {tokenStatus.days_remaining.toFixed(1)} days remaining
        </p>
      )}

      {isExpiring && (
        <div
          className={`rounded border p-3 text-sm ${
            tokenStatus.status === "expired"
              ? "border-tf-negative/20 bg-tf-negative/10 text-tf-negative"
              : "border-tf-warning/20 bg-tf-warning/10 text-tf-warning"
          }`}
        >
          {tokenStatus.message}
        </div>
      )}

      {showPasteFlow && (
        <div className="space-y-2 rounded border border-tf-border-default p-3">
          <p className="text-xs text-tf-text-secondary">
            A Schwab authorization page has opened in a new tab. After
            authorizing, copy the full URL from your browser's address bar
            and paste it below.
          </p>
          <input
            type="text"
            value={redirectUrl}
            onChange={(e) => setRedirectUrl(e.target.value)}
            placeholder="Paste redirect URL here..."
            className="w-full rounded border border-tf-border-default bg-tf-bg-surface px-3 py-2 text-sm text-tf-text-primary placeholder:text-tf-text-tertiary"
          />
          <div className="flex gap-2">
            <button
              onClick={handleExchange}
              disabled={exchanging || !redirectUrl.trim()}
              className="rounded bg-tf-accent-primary px-3 py-1 text-xs font-medium text-white hover:bg-tf-accent-primary/90 disabled:opacity-50"
            >
              {exchanging ? "Exchanging..." : "Complete Authorization"}
            </button>
            <button
              onClick={handleCancel}
              className="rounded border border-tf-border-default px-3 py-1 text-xs font-medium text-tf-text-secondary hover:bg-tf-bg-elevated"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && <p className="text-xs text-tf-negative">{error}</p>}
      {success && <p className="text-xs text-tf-positive">{success}</p>}
    </div>
  );
}
