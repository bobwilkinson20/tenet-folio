import { useCallback, useEffect, useRef, useState } from "react";
import {
  usePlaidLink,
  type PlaidLinkError,
  type PlaidLinkOnExitMetadata,
} from "react-plaid-link";
import { plaidApi } from "@/api/plaid";

interface PlaidUpdateButtonProps {
  itemId: string;
  onSuccess?: () => void;
}

export function PlaidUpdateButton({ itemId, onSuccess }: PlaidUpdateButtonProps) {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasOpened = useRef(false);

  const fetchUpdateToken = useCallback(async () => {
    setLoading(true);
    setError(null);
    hasOpened.current = false;
    try {
      const response = await plaidApi.createUpdateLinkToken(itemId);
      setLinkToken(response.data.link_token);
    } catch {
      setError("Failed to start update");
    } finally {
      setLoading(false);
    }
  }, [itemId]);

  const handlePlaidSuccess = useCallback(async () => {
    try {
      await plaidApi.clearItemError(itemId);
      setLinkToken(null);
      onSuccess?.();
    } catch {
      setError("Failed to clear error state");
    }
  }, [itemId, onSuccess]);

  const handleExit = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    (err: PlaidLinkError | null, _metadata: PlaidLinkOnExitMetadata) => {
      if (err) {
        const msg =
          err.display_message ||
          err.error_message ||
          err.error_code ||
          "Update closed with an error";
        setError(msg);
      }
      setLinkToken(null);
    },
    [],
  );

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess: handlePlaidSuccess,
    onExit: handleExit,
  });

  useEffect(() => {
    if (linkToken && ready && !hasOpened.current) {
      hasOpened.current = true;
      open();
    }
  }, [linkToken, ready, open]);

  return (
    <div>
      <button
        onClick={fetchUpdateToken}
        disabled={loading || !!linkToken}
        className="rounded-md bg-tf-accent-primary px-2 py-1 text-xs font-medium text-white hover:bg-tf-accent-primary/90 disabled:opacity-50"
      >
        {loading ? "Loading..." : "Update"}
      </button>
      {error && <p className="mt-1 text-xs text-tf-negative">{error}</p>}
    </div>
  );
}
