import { useCallback, useEffect, useRef, useState } from "react";
import {
  usePlaidLink,
  type PlaidLinkError,
  type PlaidLinkOnExitMetadata,
  type PlaidLinkOnEventMetadata,
  type PlaidLinkOnSuccessMetadata,
} from "react-plaid-link";
import { plaidApi } from "@/api/plaid";

interface PlaidLinkButtonProps {
  onSuccess?: () => void;
}

export function PlaidLinkButton({ onSuccess }: PlaidLinkButtonProps) {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasOpened = useRef(false);

  const fetchLinkToken = async () => {
    setLoading(true);
    setError(null);
    hasOpened.current = false;
    try {
      const response = await plaidApi.createLinkToken();
      setLinkToken(response.data.link_token);
    } catch {
      setError("Failed to create link token");
    } finally {
      setLoading(false);
    }
  };

  const handlePlaidSuccess = useCallback(
    async (publicToken: string, metadata: PlaidLinkOnSuccessMetadata) => {
      try {
        await plaidApi.exchangeToken(
          publicToken,
          metadata.institution?.institution_id,
          metadata.institution?.name,
        );
        setLinkToken(null);
        onSuccess?.();
      } catch {
        setError("Failed to link institution");
      }
    },
    [onSuccess],
  );

  const handleExit = useCallback(
    (err: PlaidLinkError | null, _metadata: PlaidLinkOnExitMetadata) => {
      if (err) {
        const msg = err.display_message || err.error_message || err.error_code || "Plaid Link closed with an error";
        setError(msg);
      }
      setLinkToken(null);
    },
    [],
  );

  const handleEvent = useCallback(
    (_eventName: string, _metadata: PlaidLinkOnEventMetadata) => {
      // Available for debugging: uncomment to trace Plaid Link events
      // console.log("[Plaid Link] event:", _eventName, _metadata);
    },
    [],
  );

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess: handlePlaidSuccess,
    onExit: handleExit,
    onEvent: handleEvent,
  });

  // Open Plaid Link once when the token is ready
  useEffect(() => {
    if (linkToken && ready && !hasOpened.current) {
      hasOpened.current = true;
      open();
    }
  }, [linkToken, ready, open]);

  return (
    <div>
      <button
        onClick={fetchLinkToken}
        disabled={loading}
        className="rounded-md bg-tf-accent-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-tf-accent-primary/90 disabled:opacity-50"
      >
        {loading ? "Loading..." : "Link Institution"}
      </button>
      {error && (
        <p className="mt-1 text-xs text-tf-negative">{error}</p>
      )}
    </div>
  );
}
