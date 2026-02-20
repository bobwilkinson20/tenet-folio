"""Unit tests for the provider exception hierarchy."""

import pytest

from integrations.exceptions import (
    ProviderAPIError,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderDataError,
    ProviderError,
)


class TestExceptionHierarchy:
    """All provider exceptions are caught by except ProviderError."""

    def test_provider_auth_error_is_provider_error(self):
        exc = ProviderAuthError("bad creds", provider_name="SimpleFIN")
        assert isinstance(exc, ProviderError)

    def test_provider_connection_error_is_provider_error(self):
        exc = ProviderConnectionError("timeout", provider_name="IBKR")
        assert isinstance(exc, ProviderError)

    def test_provider_api_error_is_provider_error(self):
        exc = ProviderAPIError("500 error", provider_name="Schwab", status_code=500)
        assert isinstance(exc, ProviderError)

    def test_provider_data_error_is_provider_error(self):
        exc = ProviderDataError("bad json", provider_name="Coinbase")
        assert isinstance(exc, ProviderError)

    def test_catch_all_provider_errors(self):
        """A single except ProviderError catches all subtypes."""
        exceptions = [
            ProviderAuthError("auth", provider_name="A"),
            ProviderConnectionError("conn", provider_name="B"),
            ProviderAPIError("api", provider_name="C", status_code=400),
            ProviderDataError("data", provider_name="D"),
        ]
        for exc in exceptions:
            with pytest.raises(ProviderError):
                raise exc


class TestProviderAPIErrorRetriable:
    """ProviderAPIError.retriable depends on status_code."""

    def test_429_is_retriable(self):
        exc = ProviderAPIError("rate limit", status_code=429)
        assert exc.retriable is True

    def test_500_is_retriable(self):
        exc = ProviderAPIError("server error", status_code=500)
        assert exc.retriable is True

    def test_503_is_retriable(self):
        exc = ProviderAPIError("unavailable", status_code=503)
        assert exc.retriable is True

    def test_400_is_not_retriable(self):
        exc = ProviderAPIError("bad request", status_code=400)
        assert exc.retriable is False

    def test_401_is_not_retriable(self):
        exc = ProviderAPIError("unauthorized", status_code=401)
        assert exc.retriable is False

    def test_none_status_is_not_retriable(self):
        exc = ProviderAPIError("unknown")
        assert exc.retriable is False


class TestExceptionStr:
    """str() on all exception types returns the message."""

    def test_provider_error_str(self):
        exc = ProviderError("something broke", provider_name="Test")
        assert str(exc) == "something broke"

    def test_provider_auth_error_str(self):
        exc = ProviderAuthError("bad creds", provider_name="SimpleFIN")
        assert str(exc) == "bad creds"

    def test_provider_connection_error_str(self):
        exc = ProviderConnectionError("timeout", provider_name="IBKR")
        assert str(exc) == "timeout"

    def test_provider_api_error_str(self):
        exc = ProviderAPIError("HTTP 500", provider_name="Schwab", status_code=500)
        assert str(exc) == "HTTP 500"

    def test_provider_data_error_str(self):
        exc = ProviderDataError("bad json", provider_name="Coinbase")
        assert str(exc) == "bad json"


class TestExceptionAttributes:
    """Exception attributes are properly set."""

    def test_provider_name_stored(self):
        exc = ProviderError("msg", provider_name="TestProvider")
        assert exc.provider_name == "TestProvider"

    def test_connection_error_retriable_default(self):
        exc = ProviderConnectionError("timeout", provider_name="X")
        assert exc.retriable is True

    def test_connection_error_retriable_override(self):
        exc = ProviderConnectionError("permanent", provider_name="X", retriable=False)
        assert exc.retriable is False

    def test_api_error_status_code(self):
        exc = ProviderAPIError("error", status_code=403)
        assert exc.status_code == 403
