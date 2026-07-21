#!/usr/bin/env python3
"""Prepare mode-0600 staging env files without printing secret values."""

from __future__ import annotations

import argparse
import base64
import os
import re
import stat
import sys
from pathlib import Path
from urllib.parse import quote


CANDIDATE = "ff07ce47d20f3f6eb09d633b09292628fbb58e2a"
STAGING_HOST = "staging-vnext.muchenai.com"
IMAGES = {
    "API_IMAGE": "ghcr.io/muchenai2024-creator/muchen-journey-vnext-api@sha256:6f9c8badc778d1344b920c8173dd3771c69642eec7d9747a2e4218ca987247c0",
    "WEB_IMAGE": "ghcr.io/muchenai2024-creator/muchen-journey-vnext-web@sha256:239b27949a9ef2137d1383bc459169e2794dbbe0d88fbfd4953d16f446e0917a",
    "WORKER_IMAGE": "ghcr.io/muchenai2024-creator/muchen-journey-vnext-worker@sha256:fd679e07ea7a0ab5d5feb5c3bacb6c41d7c1e82db621cf76fe8b90c3eadade27",
}
SECRET_NAMES = (
    "WP08_MIGRATION_DB_PASSWORD",
    "WP08_RUNTIME_DB_PASSWORD",
    "WP08_SESSION_SECRET",
    "WP08_INVITE_SECRET",
    "WP08_IMPORT_SIGNING_KEY",
    "WP08_RDS_CA_PEM_B64",
)


class PrepareError(RuntimeError):
    pass


def required_environment() -> dict[str, str]:
    values: dict[str, str] = {}
    for name in (*SECRET_NAMES, "WP08_ACME_EMAIL"):
        value = os.getenv(name, "")
        if not value:
            raise PrepareError(f"required environment variable is absent: {name}")
        if "\n" in value or "\r" in value:
            raise PrepareError(f"environment variable contains a newline: {name}")
        values[name] = value
    independent = {
        values["WP08_MIGRATION_DB_PASSWORD"],
        values["WP08_RUNTIME_DB_PASSWORD"],
        values["WP08_SESSION_SECRET"],
        values["WP08_INVITE_SECRET"],
        values["WP08_IMPORT_SIGNING_KEY"],
    }
    if len(independent) != 5:
        raise PrepareError("database and application secrets must all be independent")
    minimum_length_secrets = (
        "WP08_SESSION_SECRET",
        "WP08_INVITE_SECRET",
        "WP08_IMPORT_SIGNING_KEY",
    )
    for name in minimum_length_secrets:
        if len(values[name]) < 32:
            raise PrepareError(f"{name} must contain at least 32 characters")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", values["WP08_ACME_EMAIL"]):
        raise PrepareError("WP08_ACME_EMAIL is invalid")
    return values


def dsn(user: str, password: str, host: str, port: int) -> str:
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/journey_next_staging"
        "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
    )


def write_env(path: Path, values: dict[str, str]) -> None:
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise PrepareError(f"invalid env key: {key}")
        if "\n" in value or "\r" in value:
            raise PrepareError(f"env value contains newline: {key}")
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(0o600)


def prepare(output: Path, host: str, port: int) -> None:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or host in {"localhost", "127.0.0.1"}:
        raise PrepareError("RDS host must be one non-local DNS name")
    if port < 1 or port > 65535:
        raise PrepareError("RDS port is invalid")
    values = required_environment()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    secrets = output / "secrets"
    secrets.mkdir(mode=0o700)

    runtime_url = dsn(
        "journey_next_runtime", values["WP08_RUNTIME_DB_PASSWORD"], host, port
    )
    migration_url = dsn(
        "journey_next_migrator", values["WP08_MIGRATION_DB_PASSWORD"], host, port
    )
    shared_api = {
        "APP_ENV": "staging",
        "APP_RELEASE": CANDIDATE,
        "CONFIG_SCHEMA_VERSION": "1",
        "ALLOWED_HOSTS": f"{STAGING_HOST},api,localhost,127.0.0.1",
        "ALLOW_FIXTURE_IDENTITY": "false",
        "SESSION_SECRET": values["WP08_SESSION_SECRET"],
        "INVITE_SECRET": values["WP08_INVITE_SECRET"],
        "IMPORT_SIGNING_KEY": values["WP08_IMPORT_SIGNING_KEY"],
        "ATTACHMENT_STORAGE_ROOT": "/srv/journey-next-staging/attachments",
    }
    write_env(secrets / "api.env", {**shared_api, "DATABASE_URL": runtime_url})
    write_env(secrets / "migration.env", {**shared_api, "DATABASE_URL": migration_url})
    write_env(
        secrets / "worker.env",
        {
            "APP_ENV": "staging",
            "APP_RELEASE": CANDIDATE,
            "DATABASE_URL": runtime_url,
            "NOTIFICATION_ADAPTER": "DISABLED",
            "NOTIFICATION_MAX_ATTEMPTS": "3",
            "NOTIFICATION_RETRY_BASE_SECONDS": "5",
            "OUTBOX_LEASE_SECONDS": "30",
            "WORKER_POLL_SECONDS": "2",
        },
    )
    write_env(
        secrets / "web.env",
        {
            "APP_ENV": "staging",
            "APP_RELEASE": CANDIDATE,
            "CONFIG_SCHEMA_VERSION": "1",
            "API_INTERNAL_URL": "http://api:8000",
            "ALLOW_FIXTURE_IDENTITY": "false",
        },
    )
    write_env(
        secrets / "edge.env",
        {
            "STAGING_HOST": STAGING_HOST,
            "ACME_EMAIL": values["WP08_ACME_EMAIL"],
        },
    )
    try:
        ca_bytes = base64.b64decode(values["WP08_RDS_CA_PEM_B64"], validate=True)
    except ValueError as error:
        raise PrepareError("WP08_RDS_CA_PEM_B64 is not valid base64") from error
    if b"-----BEGIN CERTIFICATE-----" not in ca_bytes or b"-----END CERTIFICATE-----" not in ca_bytes:
        raise PrepareError("decoded RDS CA is not PEM")
    ca_path = secrets / "volcengine-rds-ca.pem"
    ca_path.write_bytes(ca_bytes)
    ca_path.chmod(0o600)
    write_env(
        output / ".deployment.env",
        {
            "CANDIDATE_COMMIT": CANDIDATE,
            "STAGING_HOST": STAGING_HOST,
            **IMAGES,
        },
    )
    for path in (*secrets.iterdir(), output / ".deployment.env"):
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise PrepareError(f"incorrect mode for {path.name}")
    print(f"WP08_DEPLOY_BUNDLE=READY path={output} secret_files=6")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rds-host", required=True)
    parser.add_argument("--rds-port", type=int, required=True)
    args = parser.parse_args()
    try:
        prepare(args.output, args.rds_host, args.rds_port)
    except (OSError, PrepareError) as error:
        print(f"WP08_PREPARE_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
