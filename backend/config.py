"""Application configuration using pydantic-settings."""

from typing import Any

from pydantic import field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from services.credential_manager import CREDENTIAL_KEYS, get_credential


class KeychainSettingsSource(PydanticBaseSettingsSource):
    """Load credential fields from macOS Keychain via ``keyring``.

    Only fields whose uppercase name appears in
    :data:`~services.credential_manager.CREDENTIAL_KEYS` are looked up.
    All other fields return ``None`` so the next source in the chain
    handles them.
    """

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        env_name = field_name.upper()
        if env_name not in CREDENTIAL_KEYS:
            return None, field_name, False
        value = get_credential(env_name)
        return value, field_name, False

    def __call__(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for field_name, field_info in self.settings_cls.model_fields.items():
            value, key, is_complex = self.get_field_value(field_info, field_name)
            if value is not None:
                d[key] = value
        return d


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            KeychainSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    # Database
    DATABASE_URL: str = "sqlite:///./portfolio.db"
    SQLCIPHER_KEY: str = ""

    # SnapTrade credentials (optional - for SnapTrade integration)
    SNAPTRADE_CLIENT_ID: str = ""
    SNAPTRADE_CONSUMER_KEY: str = ""
    SNAPTRADE_USER_ID: str = ""
    SNAPTRADE_USER_SECRET: str = ""

    # SimpleFIN credentials (optional - for SimpleFIN integration)
    SIMPLEFIN_ACCESS_URL: str = ""

    # Interactive Brokers Flex Web Service credentials (optional)
    IBKR_FLEX_TOKEN: str = ""
    IBKR_FLEX_QUERY_ID: str = ""

    # Coinbase Advanced Trade API credentials (optional)
    COINBASE_API_KEY: str = ""
    COINBASE_API_SECRET: str = ""
    COINBASE_KEY_FILE: str = ""

    # Charles Schwab API credentials (optional)
    SCHWAB_APP_KEY: str = ""
    SCHWAB_APP_SECRET: str = ""
    SCHWAB_CALLBACK_URL: str = "https://127.0.0.1"
    SCHWAB_TOKEN_PATH: str = ""

    @field_validator("COINBASE_API_SECRET", mode="before")
    @classmethod
    def normalize_pem_newlines(cls, v: str) -> str:
        """Convert literal ``\\n`` sequences to real newlines in PEM secrets.

        When set via shell ``export``, ``\\n`` stays as a literal two-char
        sequence. python-dotenv already converts ``\\n`` inside double-quoted
        ``.env`` values, so this handles the shell-export case.
        """
        if isinstance(v, str) and "\\n" in v:
            v = v.replace("\\n", "\n")
        return v

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate and normalize LOG_LEVEL to an uppercase Python logging level."""
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}, got {v!r}")
        return v.upper()

    # App settings
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"


settings = Settings()
