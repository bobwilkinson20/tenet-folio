"""Typed exception hierarchy for provider errors.

Provides structured exceptions for differentiated error handling
(auth errors vs transient network errors vs data issues).
"""


class ProviderError(Exception):
    """Base exception for all provider-related errors.

    Carries the provider name so callers can identify which provider failed.
    """

    def __init__(self, message: str, provider_name: str = ""):
        self.provider_name = provider_name
        super().__init__(message)


class ProviderAuthError(ProviderError):
    """Credentials missing, expired, or invalid (HTTP 401/403)."""

    pass


class ProviderConnectionError(ProviderError):
    """Network failures — timeouts, DNS resolution, connection refused.

    Retriable by default.
    """

    def __init__(self, message: str, provider_name: str = "", retriable: bool = True):
        self.retriable = retriable
        super().__init__(message, provider_name)


class ProviderAPIError(ProviderError):
    """HTTP 4xx/5xx responses from the provider API."""

    def __init__(
        self,
        message: str,
        provider_name: str = "",
        status_code: int | None = None,
    ):
        self.status_code = status_code
        super().__init__(message, provider_name)

    @property
    def retriable(self) -> bool:
        """429 (rate limit) and 5xx errors are generally retriable."""
        if self.status_code is None:
            return False
        return self.status_code == 429 or self.status_code >= 500


class ProviderDataError(ProviderError):
    """Malformed or unparseable response from the provider."""

    pass
