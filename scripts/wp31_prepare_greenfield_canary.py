#!/usr/bin/env python3
"""Create the owner-only, zero-worker Greenfield Production Canary bundle."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

try:
    from scripts.wp31_candidate_binding import BindingError, verify_binding
except ModuleNotFoundError:  # direct invocation from the scripts directory
    from wp31_candidate_binding import BindingError, verify_binding


ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "config/wp31_candidate_binding.json"
CANDIDATE = "0e86352d109fd49c7e4f4fc26d36a14822dc7219"
PRODUCTION_HOST = "journey.muchenai.com"
SOURCE_DATABASE = "journey_next_cutover_20260810"
CANARY_DATABASE = "journey_next_canary_20260901_c72fea5"
IMAGES = {
    "API_IMAGE": "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:01e74f77faf364e65d157403262676f19d98f4862cd5ee0a80396fac91a7bce8",
    "WEB_IMAGE": "ghcr.io/muchenai/muchen-journey-vnext-web@sha256:5408e32b62ce8a2b954c63fecd8863ecd631cdb66ca82ab9d14adbb34e68cdd5",
}
DBTOOL_IMAGE = "ghcr.io/muchenai2024-creator/muchen-journey-vnext-dbtool@sha256:3a82828474772d2b9c94fb51ae343e464c2f13dd1f2d7d90c807a46b104f53e9"


class PrepareCanaryError(RuntimeError):
    pass


def candidate_binding() -> dict[str, object]:
    try:
        return verify_binding(BINDING)
    except BindingError as error:
        raise PrepareCanaryError("candidate binding is invalid") from error


def bound_candidate_and_images() -> tuple[str, dict[str, str]]:
    binding = candidate_binding()
    candidate = str(binding["application_candidate_sha"])
    raw_images = binding["images"]
    assert isinstance(raw_images, dict)
    images = {
        "API_IMAGE": f"ghcr.io/muchenai/muchen-journey-vnext-api@{raw_images['api']['registry_digest']}",
        "WEB_IMAGE": f"ghcr.io/muchenai/muchen-journey-vnext-web@{raw_images['web']['registry_digest']}",
    }
    return candidate, images


def require(name: str, minimum: int = 1) -> str:
    value = os.getenv(name, "")
    if len(value) < minimum or "\n" in value or "\r" in value:
        raise PrepareCanaryError(f"required environment variable is invalid: {name}")
    return value


def allowlist() -> tuple[str, int, str]:
    raw = os.getenv("WP31_CANARY_LEARNER_USER_IDS", "")
    values = [item.strip() for item in raw.split(",") if item.strip()]
    try:
        canonical = [str(UUID(item)) for item in values]
    except ValueError as error:
        raise PrepareCanaryError("canary learner allowlist is invalid") from error
    if len(canonical) != len(set(canonical)) or len(canonical) > 8:
        raise PrepareCanaryError("canary learner allowlist must be unique and contain at most 8 IDs")
    joined = ",".join(sorted(canonical))
    return joined, len(canonical), hashlib.sha256(joined.encode()).hexdigest()


def dsn(user: str, password: str, host: str, port: int, database: str) -> str:
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{database}"
        "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
    )


def write_env(path: Path, values: dict[str, str], mode: int = 0o600) -> None:
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or "\n" in value or "\r" in value:
            raise PrepareCanaryError(f"unsafe env value: {key}")
    with path.open("x", encoding="utf-8") as handle:
        handle.write("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(mode)


def prepare(output: Path, host: str, port: int) -> None:
    if output.exists() or output.is_symlink():
        raise PrepareCanaryError("output must not already exist")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or host in {"localhost", "127.0.0.1"}:
        raise PrepareCanaryError("RDS host is invalid")
    if not 1 <= port <= 65535:
        raise PrepareCanaryError("RDS port is invalid")

    candidate, images = bound_candidate_and_images()
    migration_password = require("WP08_MIGRATION_DB_PASSWORD", 20)
    runtime_password = require("WP08_RUNTIME_DB_PASSWORD", 20)
    session_secret = require("WP15_SESSION_SECRET", 32)
    invite_secret = require("WP15_INVITE_SECRET", 32)
    import_key = require("WP15_IMPORT_SIGNING_KEY", 32)
    backup_key = require("WP15_BACKUP_KEY", 32)
    identity_secret = require("WP09_IDENTITY_SUBJECT_SECRET", 32)
    feishu_app_id = require("WP09_FEISHU_APP_ID", 3)
    feishu_app_secret = require("WP09_FEISHU_APP_SECRET", 16)
    ca_b64 = require("WP08_RDS_CA_PEM_B64", 20)
    if len({session_secret, invite_secret, import_key, backup_key}) != 4:
        raise PrepareCanaryError("application and backup secrets must be independent")
    learner_ids, learner_count, allowlist_sha = allowlist()

    output.mkdir(parents=True, mode=0o700)
    secrets = output / "secrets"
    secrets.mkdir(mode=0o700)
    runtime_url = dsn("journey_next_runtime", runtime_password, host, port, CANARY_DATABASE)
    migration_url = dsn("journey_next_migrator", migration_password, host, port, CANARY_DATABASE)
    source_url = dsn("journey_next_migrator", migration_password, host, port, SOURCE_DATABASE)
    shared = {
        "APP_ENV": "production",
        "APP_RELEASE": candidate,
        "CONFIG_SCHEMA_VERSION": "3",
        "RELEASE_MARKER": "PRODUCTION_CANARY_UAT",
        "CANARY_LEARNER_USER_IDS": learner_ids,
        "ALLOWED_HOSTS": f"{PRODUCTION_HOST},greenfield-canary-api,localhost,127.0.0.1",
        "ALLOW_FIXTURE_IDENTITY": "false",
        "SESSION_SECRET": session_secret,
        "INVITE_SECRET": invite_secret,
        "IMPORT_SIGNING_KEY": import_key,
        "IDENTITY_SUBJECT_SECRET": identity_secret,
        "FEISHU_OAUTH_ENABLED": "true",
        "FEISHU_APP_ID": feishu_app_id,
        "FEISHU_APP_SECRET": feishu_app_secret,
        "FEISHU_OAUTH_REDIRECT_URI": f"https://{PRODUCTION_HOST}/auth/feishu/callback",
        "ATTACHMENTS_ENABLED": "false",
        "NOTIFICATION_CHANNEL": "FEISHU",
        "NOTIFICATION_RECIPIENTS_ENABLED": "false",
        "DB_POOL_SIZE": "8",
        "DB_MAX_OVERFLOW": "2",
        "DB_POOL_TIMEOUT_SECONDS": "5",
    }
    write_env(secrets / "api.env", {**shared, "DATABASE_URL": runtime_url})
    write_env(secrets / "migration.env", {**shared, "DATABASE_URL": migration_url})
    write_env(secrets / "source-facts.env", {**shared, "DATABASE_URL": source_url})
    write_env(secrets / "target-facts.env", {**shared, "DATABASE_URL": migration_url})
    write_env(
        secrets / "web.env",
        {
            "APP_ENV": "production",
            "APP_RELEASE": candidate,
            "CONFIG_SCHEMA_VERSION": "3",
            "RELEASE_MARKER": "PRODUCTION_CANARY_UAT",
            "API_INTERNAL_URL": "http://greenfield-canary-api:8000",
            "ALLOW_FIXTURE_IDENTITY": "false",
        },
    )
    write_env(
        secrets / "backup.env",
        {
            "SOURCE_DATABASE": SOURCE_DATABASE,
            "TARGET_DATABASE": CANARY_DATABASE,
            "RDS_HOST": host,
            "RDS_PORT": str(port),
            "MIGRATION_DB_PASSWORD": migration_password,
            "WP15_BACKUP_KEY": backup_key,
            "DBTOOL_IMAGE": DBTOOL_IMAGE,
            "API_IMAGE": images["API_IMAGE"],
        },
    )
    try:
        ca = base64.b64decode(ca_b64, validate=True)
    except ValueError as error:
        raise PrepareCanaryError("RDS CA is invalid Base64") from error
    if b"-----BEGIN CERTIFICATE-----" not in ca:
        raise PrepareCanaryError("RDS CA is not PEM")
    ca_path = secrets / "volcengine-rds-ca.pem"
    ca_path.write_bytes(ca)
    ca_path.chmod(0o444)
    write_env(
        output / ".deployment.env",
        {
            "CANDIDATE_COMMIT": candidate,
            "PRODUCTION_HOST": PRODUCTION_HOST,
            "SOURCE_DATABASE": SOURCE_DATABASE,
            "CANARY_DATABASE": CANARY_DATABASE,
            **images,
        },
    )
    proof = {
        "schema_version": 1,
        "allowlist_count": learner_count,
        "allowlist_sha256": allowlist_sha,
        "max_allowlisted_learners": 8,
        "raw_identifiers_in_proof": False,
    }
    proof_path = output / "allowlist-proof.json"
    with proof_path.open("x", encoding="utf-8") as handle:
        json.dump(proof, handle, indent=2, sort_keys=True)
        handle.write("\n")
    proof_path.chmod(0o600)
    print(
        "WP31_GREENFIELD_CANARY_BUNDLE=READY "
        f"allowlist_count={learner_count} allowlist_sha256={allowlist_sha} "
        "worker_started=false secret_values_printed=false"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rds-host", required=True)
    parser.add_argument("--rds-port", type=int, required=True)
    args = parser.parse_args()
    try:
        prepare(args.output, args.rds_host, args.rds_port)
    except (OSError, PrepareCanaryError) as error:
        print(f"WP31_GREENFIELD_CANARY_PREPARE=FAIL reason={error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
