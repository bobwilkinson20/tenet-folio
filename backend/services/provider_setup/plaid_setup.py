"""Plaid provider setup — credential validation and storage."""

import logging

from .base import ProviderFieldDef, SetupResult, store_credentials

logger = logging.getLogger(__name__)

PROVIDER_NAME = "Plaid"

_VALID_ENVIRONMENTS = {"sandbox", "production"}

FIELDS: list[ProviderFieldDef] = [
    {
        "key": "client_id",
        "label": "Client ID",
        "help_text": "Your Plaid client_id from the Developers > Keys page.",
        "input_type": "password",
        "store_key": "PLAID_CLIENT_ID",
    },
    {
        "key": "secret",
        "label": "Secret",
        "help_text": "Your Plaid secret for the chosen environment.",
        "input_type": "password",
        "store_key": "PLAID_SECRET",
    },
    {
        "key": "environment",
        "label": "Environment",
        "help_text": (
            "Each environment has separate API keys. "
            "Use sandbox for testing with fake data."
        ),
        "input_type": "select",
        "store_key": "PLAID_ENVIRONMENT",
        "options": [
            {"value": "sandbox", "label": "Sandbox"},
            {"value": "production", "label": "Production"},
        ],
    },
]


def validate(
    credentials: dict[str, str], fields: list[ProviderFieldDef]
) -> SetupResult:
    """Validate Plaid API credentials and store in Keychain.

    Tests the credentials by creating a test link token (same approach
    as the CLI setup script), then stores all three fields via the
    shared ``store_credentials()`` helper.
    """
    client_id = credentials.get("client_id", "").strip()
    if not client_id:
        raise ValueError("Client ID is required")

    secret = credentials.get("secret", "").strip()
    if not secret:
        raise ValueError("Secret is required")

    environment = credentials.get("environment", "sandbox").strip().lower()
    if environment not in _VALID_ENVIRONMENTS:
        raise ValueError(
            f"Invalid environment: {environment}. Must be sandbox or production."
        )

    # Inline import: plaid SDK is an optional dependency
    try:
        from plaid import Environment
        from plaid.api.plaid_api import PlaidApi
        from plaid.api_client import ApiClient
        from plaid.configuration import Configuration
        from plaid.model.country_code import CountryCode
        from plaid.model.link_token_create_request import LinkTokenCreateRequest
        from plaid.model.link_token_create_request_user import (
            LinkTokenCreateRequestUser,
        )
        from plaid.model.products import Products
    except ImportError as exc:
        raise RuntimeError(
            "Plaid library is not installed. "
            "Install it with: uv add plaid-python"
        ) from exc

    env_map = {
        "sandbox": Environment.Sandbox,
        "production": Environment.Production,
    }

    try:
        configuration = Configuration(
            host=env_map[environment],
            api_key={"clientId": client_id, "secret": secret},
        )
        api_client = ApiClient(configuration)
        api = PlaidApi(api_client)

        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id="setup-test"),
            client_name="TenetFolio",
            products=[Products("investments")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        response = api.link_token_create(request)
        assert response["link_token"], "No link_token in response"
    except Exception as exc:
        error_msg = str(exc)
        if "INVALID_API_KEYS" in error_msg:
            raise ValueError(
                "Plaid rejected the credentials. Check that the environment "
                "matches your keys — sandbox and production have different secrets."
            ) from exc
        raise ValueError(
            f"Failed to validate Plaid credentials: {exc}"
        ) from exc

    # Update credentials dict with normalized environment before storage
    credentials = {**credentials, "environment": environment}
    store_credentials(credentials, fields)

    logger.info("Plaid credentials validated and stored")
    return SetupResult(
        message="Plaid configured successfully. Credentials stored in Keychain."
    )
