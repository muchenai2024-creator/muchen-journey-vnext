import pytest
from pydantic import ValidationError

from journey_api.config import Settings


def test_fixture_identity_configuration_fails_closed_outside_local_test():
    with pytest.raises(ValidationError, match="ALLOW_FIXTURE_IDENTITY"):
        Settings(app_env="production", allow_fixture_identity=True)


def test_nonlocal_identity_requires_distinct_vnext_secrets():
    with pytest.raises(ValidationError, match="independently configured"):
        Settings(app_env="production", allow_fixture_identity=False)
    with pytest.raises(ValidationError, match="must be independent"):
        Settings(
            app_env="staging",
            allow_fixture_identity=False,
            session_secret="same-secret-value-that-is-long-enough-12345",
            invite_secret="same-secret-value-that-is-long-enough-12345",
            import_signing_key="staging-import-signing-key-example-123456",
        )
    configured = Settings(
        app_env="production",
        allow_fixture_identity=False,
        session_secret="production-session-secret-example-123456",
        invite_secret="production-invite-secret-example-1234567",
        import_signing_key="production-import-signing-key-example-123456",
    )
    assert configured.allow_fixture_identity is False


def test_config_schema_version_is_fail_closed():
    with pytest.raises(ValidationError, match="CONFIG_SCHEMA_VERSION"):
        Settings(config_schema_version=2)
