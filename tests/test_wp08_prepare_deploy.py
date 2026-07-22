import base64
import stat
from pathlib import Path

import pytest

import scripts.wp08_prepare_deploy as prepare


def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "WP08_MIGRATION_DB_PASSWORD": "Migration-Password-123!",
        "WP08_RUNTIME_DB_PASSWORD": "Runtime-Password-456!",
        "WP08_SESSION_SECRET": "session-secret-independent-000000001",
        "WP08_INVITE_SECRET": "invite-secret-independent-0000000002",
        "WP08_IMPORT_SIGNING_KEY": "import-key-independent-00000000003",
        "WP08_RDS_CA_PEM_B64": base64.b64encode(
            b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n"
        ).decode(),
        "WP08_ACME_EMAIL": "ops@example.com",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_prepare_writes_private_independent_environment_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    configure(monkeypatch)
    output = tmp_path / "bundle"
    prepare.prepare(output, "postgres.internal.example", 5432)
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    for path in [*list((output / "secrets").iterdir()), output / ".deployment.env"]:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "NOTIFICATION_ADAPTER=DISABLED" in (output / "secrets/worker.env").read_text()
    assert "ALLOW_FIXTURE_IDENTITY=false" in (output / "secrets/api.env").read_text()
    assert "Migration-Password" not in (output / "secrets/api.env").read_text()
    deployment = (output / ".deployment.env").read_text()
    assert f"CANDIDATE_COMMIT={prepare.CANDIDATE}" in deployment
    for image in prepare.IMAGES.values():
        assert image in deployment


def test_prepare_rejects_reused_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    configure(monkeypatch)
    monkeypatch.setenv("WP08_RUNTIME_DB_PASSWORD", "Migration-Password-123!")
    with pytest.raises(prepare.PrepareError, match="independent"):
        prepare.prepare(tmp_path / "bundle", "postgres.internal.example", 5432)
