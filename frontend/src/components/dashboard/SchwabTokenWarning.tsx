import { useEffect, useState } from "react";
import { schwabApi } from "@/api/schwab";
import type { SchwabTokenStatus } from "@/api/schwab";

export function SchwabTokenWarning() {
  const [status, setStatus] = useState<SchwabTokenStatus | null>(null);

  useEffect(() => {
    schwabApi
      .getTokenStatus()
      .then((res) => setStatus(res.data))
      .catch(() => {
        /* ignore — no banner if check fails */
      });
  }, []);

  if (
    !status ||
    status.status === "valid" ||
    status.status === "no_credentials" ||
    status.status === "no_token"
  ) {
    return null;
  }

  const isExpired = status.status === "expired";

  return (
    <div
      className={`border rounded-lg p-4 ${
        isExpired
          ? "bg-tf-negative/10 border-tf-negative/20"
          : "bg-tf-warning/10 border-tf-warning/20"
      }`}
      data-testid="schwab-token-warning"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          <svg
            className={`w-6 h-6 ${isExpired ? "text-tf-negative" : "text-tf-warning"}`}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3
            className={`text-sm font-medium ${isExpired ? "text-tf-negative" : "text-tf-warning"}`}
          >
            {isExpired
              ? "Schwab token expired"
              : "Schwab token expiring soon"}
          </h3>
          <p
            className={`mt-1 text-sm ${isExpired ? "text-tf-negative" : "text-tf-warning"}`}
          >
            {status.message}{" "}
            <a
              href="/settings"
              className="underline hover:no-underline"
            >
              Go to Settings to re-authorize
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
