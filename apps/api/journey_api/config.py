from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: str = "local"
    app_release: str = "dev"
    config_schema_version: int = 1
    database_url: str = "postgresql+psycopg://journey_next:journey_next_dev@localhost:5432/journey_next_dev"
    allowed_hosts: Annotated[list[str], NoDecode] = ["localhost", "127.0.0.1"]
    allow_fixture_identity: bool = False
    session_secret: str = "journey-next-local-session-secret-change-me"
    invite_secret: str = "journey-next-local-invite-secret-change-me"
    import_signing_key: str = "journey-next-local-import-signing-key-change-me"
    session_ttl_hours: int = 8
    join_context_ttl_minutes: int = 15
    invite_exchange_limit: int = 10
    attachment_storage_root: str = "/tmp/journey-next-attachments"

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def split_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("app_env")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        if value not in {"local", "test", "staging", "production"}:
            raise ValueError("APP_ENV must be local, test, staging, or production")
        return value

    @model_validator(mode="after")
    def fixture_identity_is_never_nonlocal(self) -> "Settings":
        if self.allow_fixture_identity and self.app_env not in {"local", "test"}:
            raise ValueError("ALLOW_FIXTURE_IDENTITY may only be enabled in local/test")
        if self.app_env in {"staging", "production"}:
            insecure_defaults = {
                "journey-next-local-session-secret-change-me",
                "journey-next-local-invite-secret-change-me",
                "journey-next-local-import-signing-key-change-me",
            }
            if (
                self.session_secret in insecure_defaults
                or self.invite_secret in insecure_defaults
                or self.import_signing_key in insecure_defaults
            ):
                raise ValueError("vNext secrets must be independently configured outside local/test")
        if len(self.session_secret) < 32 or len(self.invite_secret) < 32:
            raise ValueError("vNext identity secrets must contain at least 32 characters")
        if len(self.import_signing_key) < 32:
            raise ValueError("IMPORT_SIGNING_KEY must contain at least 32 characters")
        if self.session_secret == self.invite_secret:
            raise ValueError("SESSION_SECRET and INVITE_SECRET must be independent")
        if self.import_signing_key in {self.session_secret, self.invite_secret}:
            raise ValueError("IMPORT_SIGNING_KEY must be independent from identity secrets")
        if not 1 <= self.session_ttl_hours <= 24:
            raise ValueError("SESSION_TTL_HOURS must be between 1 and 24")
        if not 5 <= self.join_context_ttl_minutes <= 30:
            raise ValueError("JOIN_CONTEXT_TTL_MINUTES must be between 5 and 30")
        if not 3 <= self.invite_exchange_limit <= 100:
            raise ValueError("INVITE_EXCHANGE_LIMIT must be between 3 and 100")
        if self.config_schema_version != 1:
            raise ValueError("CONFIG_SCHEMA_VERSION must be the approved version 1")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
