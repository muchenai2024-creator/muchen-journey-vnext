#!/usr/bin/env python3
"""Fail-closed local WP-06 operations and evidence commands.

This tool is deliberately limited to the repository's Docker Compose development
and test databases. It has no staging/production target and performs no network
writes other than Docker image operations initiated separately by repository gates.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts" / "wp06"
KEY_PATH = ROOT / ".wp06-local-backup.key"
COMPOSE = ["docker", "compose", "--project-directory", str(ROOT)]
LOCAL_DATABASE = "journey_next_dev"
LOCAL_DATABASE_USER = "journey_next"
TEST_DATABASE_USER = "journey_next"
TEST_DATABASE_PASSWORD = "journey_next_test"
ALLOWED_STATUSES = {"PASS", "FAIL", "NOT_RUN"}
REQUIRED_RELEASE_CHECKS = (
    "local_automated_suite",
    "empty_database_migration",
    "persistent_database_migration_rollback",
    "compose_health",
    "http_permission_negative",
    "browser_three_viewports",
    "dependency_security_audits",
    "local_backup_isolated_restore",
    "local_alert_and_rollback_drills",
    "real_human_uat",
    "real_external_notification",
    "staging_validation",
    "production_preflight",
    "physical_acl_validation",
    "off_host_backup_restore",
    "release_approvals",
    "real_observation_window",
)
EXTERNAL_BLOCKERS = {
    "real_human_uat",
    "real_external_notification",
    "staging_validation",
    "production_preflight",
    "physical_acl_validation",
    "off_host_backup_restore",
    "release_approvals",
    "real_observation_window",
}
SAFE_RUN_ID = re.compile(r"^wp06-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
UTC = timezone.utc


class OpsError(RuntimeError):
    """Expected fail-closed operations error."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(
    command: list[str],
    *,
    stdout: BinaryIO | int | None = None,
    stdin: BinaryIO | int | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        stdin=stdin,
        stdout=subprocess.PIPE if capture else stdout,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise OpsError(f"command failed ({result.returncode}): {command[0]} {command[1]}: {stderr}")
    return result


def compose(*arguments: str, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    return run([*COMPOSE, *arguments], **kwargs)


def psql(service: str, database: str, query: str) -> str:
    result = compose(
        "exec",
        "-T",
        service,
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        LOCAL_DATABASE_USER if service == "db" else TEST_DATABASE_USER,
        "-d",
        database,
        "-At",
        "-c",
        query,
        capture=True,
    )
    return result.stdout.decode().strip()


def ensure_local_services() -> None:
    if not (ROOT / "compose.yaml").is_file():
        raise OpsError("compose.yaml is missing; refusing to guess a target")
    compose("up", "-d", "--wait", "db", "db-test")


def ensure_key() -> bytes:
    if KEY_PATH.is_symlink():
        raise OpsError("backup key must not be a symlink")
    if not KEY_PATH.exists():
        descriptor = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(secrets.token_urlsafe(64).encode())
    mode = stat.S_IMODE(KEY_PATH.stat().st_mode)
    if mode != 0o600:
        raise OpsError(f"backup key permissions must be 0600, got {mode:04o}")
    key = KEY_PATH.read_bytes().strip()
    if len(key) < 48:
        raise OpsError("backup key is unexpectedly short")
    return key


def write_private_json(path: Path, value: object) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    roots = (
        ROOT / "apps" / "api",
        ROOT / "apps" / "worker",
        ROOT / "apps" / "web" / "src",
        ROOT / "migrations",
        ROOT / "scripts",
        ROOT / "config",
        ROOT / "contracts",
    )
    files = [
        ROOT / "Makefile",
        ROOT / "compose.yaml",
        ROOT / "pyproject.toml",
        ROOT / "requirements.lock",
        ROOT / "apps" / "web" / "package-lock.json",
    ]
    for root in roots:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )
    for path in sorted(set(files)):
        relative = path.relative_to(ROOT).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def database_facts(service: str, database: str) -> dict[str, Any]:
    migration = psql(service, database, "SELECT version_num FROM alembic_version")
    counts: dict[str, int] = {}
    for table in (
        "organizations",
        "users",
        "enrollments",
        "task_definitions",
        "task_versions",
        "assignments",
        "submission_versions",
        "reviews",
        "evaluations",
        "outcomes",
        "import_batches",
    ):
        counts[table] = int(psql(service, database, f'SELECT count(*) FROM "{table}"'))
    task_fingerprint = psql(
        service,
        database,
        "SELECT md5(COALESCE(string_agg(task_definition_id::text || ':' || version::text || ':' || id::text, ',' ORDER BY task_definition_id, version), '')) FROM task_versions",
    )
    invalid_constraints = int(
        psql(service, database, "SELECT count(*) FROM pg_constraint WHERE NOT convalidated")
    )
    invariant_violations = int(
        psql(
            service,
            database,
            """
            SELECT
              (SELECT count(*) FROM enrollments e JOIN users u ON u.id=e.learner_id WHERE e.organization_id<>u.organization_id)
              + (SELECT count(*) FROM assignments a JOIN task_versions tv ON tv.id=a.task_version_id WHERE a.organization_id<>tv.organization_id OR a.task_definition_id<>tv.task_definition_id)
              + (SELECT count(*) FROM reviews r JOIN assignments a ON a.id=r.assignment_id WHERE r.organization_id<>a.organization_id)
              + (SELECT count(*) FROM outcomes o JOIN evaluations e ON e.id=o.source_evaluation_id WHERE o.organization_id<>e.organization_id)
            """,
        )
    )
    return {
        "migration_revision": migration,
        "counts": counts,
        "task_version_fingerprint": task_fingerprint,
        "invalid_constraints": invalid_constraints,
        "critical_invariant_violations": invariant_violations,
    }


def legacy_database_facts(service: str, database: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for table in (
        "organizations",
        "users",
        "enrollments",
        "task_definitions",
        "task_versions",
        "assignments",
        "submission_versions",
        "reviews",
        "evaluations",
        "outcomes",
    ):
        counts[table] = int(psql(service, database, f'SELECT count(*) FROM "{table}"'))
    return {
        "counts": counts,
        "task_version_fingerprint": psql(
            service,
            database,
            "SELECT md5(COALESCE(string_agg(task_definition_id::text || ':' || version::text || ':' || id::text, ',' ORDER BY task_definition_id, version), '')) FROM task_versions",
        ),
    }


def migration_check() -> Path:
    ensure_local_services()
    database = "journey_next_wp06_migration"
    if psql("db-test", "journey_next_test", f"SELECT 1 FROM pg_database WHERE datname='{database}'"):
        raise OpsError("migration drill target already exists; refusing to overwrite it")
    database_url = (
        f"postgresql+psycopg://{TEST_DATABASE_USER}:{TEST_DATABASE_PASSWORD}"
        f"@db-test:5432/{database}"
    )
    created = False
    try:
        compose("exec", "-T", "db-test", "createdb", "-U", TEST_DATABASE_USER, database)
        created = True
        compose(
            "run", "--rm", "--no-deps", "-e", f"DATABASE_URL={database_url}",
            "api", "alembic", "upgrade", "0009_notification_scope",
        )
        compose(
            "run", "--rm", "--no-deps", "-e", f"DATABASE_URL={database_url}",
            "api", "python", "-m", "journey_api.seed",
        )
        before = legacy_database_facts("db-test", database)
        compose(
            "run", "--rm", "--no-deps", "-e", f"DATABASE_URL={database_url}",
            "api", "alembic", "upgrade", "head",
        )
        upgraded = database_facts("db-test", database)
        if upgraded["migration_revision"] != "0010_wp06_governance":
            raise OpsError("persistent migration drill did not reach WP-06 head")
        compose(
            "run", "--rm", "--no-deps", "-e", f"DATABASE_URL={database_url}",
            "api", "alembic", "downgrade", "0009_notification_scope",
        )
        after_downgrade = legacy_database_facts("db-test", database)
        if after_downgrade != before:
            raise OpsError("WP-06 downgrade changed pre-existing business facts")
        compose(
            "run", "--rm", "--no-deps", "-e", f"DATABASE_URL={database_url}",
            "api", "alembic", "upgrade", "head",
        )
        reupgraded = database_facts("db-test", database)
        if reupgraded != upgraded:
            raise OpsError("WP-06 re-upgrade changed persistent business facts")
        directory = make_run_directory()
        report = directory / "persistent-migration-report.json"
        write_private_json(
            report,
            {
                    "schema_version": 1,
                    "completed_at": utc_now().isoformat(),
                    "scope": "ISOLATED_LOCAL_PERSISTENT_DRILL",
                    "upgrade_0009_to_0010": "PASS",
                    "downgrade_0010_to_0009": "PASS",
                    "reupgrade_to_0010": "PASS",
                    "business_facts_preserved": True,
                    "facts": reupgraded,
            },
        )
        return report
    finally:
        if created:
            compose(
                "exec", "-T", "db-test", "dropdb", "-U", TEST_DATABASE_USER,
                "--if-exists", database,
            )


def make_run_directory() -> Path:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    run_id = f"wp06-{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    directory = ARTIFACT_ROOT / run_id
    directory.mkdir(mode=0o700)
    return directory


def backup() -> Path:
    ensure_local_services()
    key = ensure_key()
    directory = make_run_directory()
    plain = directory / "journey-next.dump"
    encrypted = directory / "journey-next.dump.enc"
    try:
        with plain.open("wb") as output:
            compose(
                "exec",
                "-T",
                "db",
                "pg_dump",
                "-U",
                LOCAL_DATABASE_USER,
                "-d",
                LOCAL_DATABASE,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                stdout=output,
        )
        plain_checksum = sha256_file(plain)
        descriptor = os.open(encrypted, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        run(
            [
                "openssl",
                "enc",
                "-aes-256-cbc",
                "-pbkdf2",
                "-salt",
                "-in",
                str(plain),
                "-out",
                str(encrypted),
                "-pass",
                f"file:{KEY_PATH}",
            ]
        )
        os.chmod(encrypted, 0o600)
        facts = database_facts("db", LOCAL_DATABASE)
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "run_id": directory.name,
            "created_at": utc_now().isoformat(),
            "scope": "LOCAL_COMPOSE_ONLY",
            "source_database": LOCAL_DATABASE,
            "encryption": "AES-256-CBC/PBKDF2",
            "plaintext_sha256": plain_checksum,
            "encrypted_sha256": sha256_file(encrypted),
            "backup_file": encrypted.name,
            "config_schema_version": 1,
            "app_release": "wp06-local-no-head",
            "source_fingerprint_sha256": source_fingerprint(),
            "openapi_sha256": sha256_file(ROOT / "contracts" / "openapi.json"),
            "database_facts": facts,
            "off_host_copy": "NOT_RUN",
            "production_backup": "NOT_RUN",
        }
        manifest["manifest_hmac_sha256"] = hmac.new(
            key, canonical_json(manifest), hashlib.sha256
        ).hexdigest()
        manifest_path = directory / "backup-manifest.json"
        write_private_json(manifest_path, manifest)
        return manifest_path
    finally:
        if plain.exists():
            plain.unlink()


def load_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    key = ensure_key()
    manifest = json.loads(path.read_text())
    signature = manifest.pop("manifest_hmac_sha256", None)
    expected = hmac.new(key, canonical_json(manifest), hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise OpsError("backup manifest signature is invalid")
    manifest["manifest_hmac_sha256"] = signature
    if manifest.get("scope") != "LOCAL_COMPOSE_ONLY":
        raise OpsError("only LOCAL_COMPOSE_ONLY backups are accepted")
    if not SAFE_RUN_ID.fullmatch(str(manifest.get("run_id", ""))):
        raise OpsError("backup run id is invalid")
    if manifest.get("backup_file") != "journey-next.dump.enc":
        raise OpsError("backup manifest file name is invalid")
    return manifest, key


def latest_manifest() -> Path:
    manifests = sorted(ARTIFACT_ROOT.glob("wp06-*/backup-manifest.json"))
    if not manifests:
        raise OpsError("no WP-06 local backup manifest exists")
    return manifests[-1]


def drill(manifest_path: Path) -> Path:
    ensure_local_services()
    manifest, _ = load_manifest(manifest_path)
    encrypted = manifest_path.parent / str(manifest["backup_file"])
    if not encrypted.is_file() or sha256_file(encrypted) != manifest["encrypted_sha256"]:
        raise OpsError("encrypted backup checksum mismatch")
    database = f"journey_next_restore_{str(manifest['run_id'])[-8:]}"
    if not re.fullmatch(r"journey_next_restore_[0-9a-f]{8}", database):
        raise OpsError("isolated restore database name is invalid")
    if psql("db-test", "journey_next_test", f"SELECT 1 FROM pg_database WHERE datname='{database}'"):
        raise OpsError("isolated restore target already exists; non-empty/unknown targets are refused")
    report_path = manifest_path.parent / "restore-rollback-report.json"
    created = False
    with tempfile.NamedTemporaryFile(prefix="wp06-restore-", suffix=".dump") as plain:
        run(
            [
                "openssl",
                "enc",
                "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-in",
                str(encrypted),
                "-out",
                plain.name,
                "-pass",
                f"file:{KEY_PATH}",
            ]
        )
        if sha256_file(Path(plain.name)) != manifest["plaintext_sha256"]:
            raise OpsError("decrypted backup checksum mismatch")
        try:
            compose("exec", "-T", "db-test", "createdb", "-U", TEST_DATABASE_USER, database)
            created = True
            with open(plain.name, "rb") as source:
                compose(
                    "exec",
                    "-T",
                    "db-test",
                    "pg_restore",
                    "-U",
                    TEST_DATABASE_USER,
                    "-d",
                    database,
                    "--no-owner",
                    "--no-privileges",
                    "--exit-on-error",
                    stdin=source,
                )
            restored = database_facts("db-test", database)
            if restored != manifest["database_facts"]:
                raise OpsError("restored database facts do not match the signed backup manifest")
            database_url = (
                f"postgresql+psycopg://{TEST_DATABASE_USER}:{TEST_DATABASE_PASSWORD}"
                f"@db-test:5432/{database}"
            )
            compose(
                "run",
                "--rm",
                "--no-deps",
                "-e",
                f"DATABASE_URL={database_url}",
                "api",
                "alembic",
                "downgrade",
                "0009_notification_scope",
            )
            rollback_revision = psql("db-test", database, "SELECT version_num FROM alembic_version")
            if rollback_revision != "0009_notification_scope":
                raise OpsError("migration rollback did not reach 0009_notification_scope")
            compose(
                "run",
                "--rm",
                "--no-deps",
                "-e",
                f"DATABASE_URL={database_url}",
                "api",
                "alembic",
                "upgrade",
                "head",
            )
            upgraded = database_facts("db-test", database)
            if upgraded != restored:
                raise OpsError("rollback/re-upgrade changed restored business facts")
            report = {
                "schema_version": 1,
                "run_id": manifest["run_id"],
                "completed_at": utc_now().isoformat(),
                "scope": "ISOLATED_LOCAL_COMPOSE_DB_TEST",
                "restore": "PASS",
                "rollback_to": rollback_revision,
                "reupgrade": "PASS",
                "database_facts": upgraded,
                "production_restore": "NOT_RUN",
                "off_host_restore": "NOT_RUN",
            }
            write_private_json(report_path, report)
        finally:
            if created:
                compose(
                    "exec",
                    "-T",
                    "db-test",
                    "dropdb",
                    "-U",
                    TEST_DATABASE_USER,
                    "--if-exists",
                    database,
                )
    return report_path


def alert_decisions(metrics: dict[str, Any]) -> list[str]:
    alerts: list[str] = []
    if metrics.get("worker_stale") is True:
        alerts.append("WORKER_STALE")
    if int(metrics.get("outbox_backlog", 0)) >= 10:
        alerts.append("OUTBOX_BACKLOG_HIGH")
    if int(metrics.get("notification_dead", 0)) > 0:
        alerts.append("NOTIFICATION_DEAD")
    if metrics.get("api_release") != metrics.get("worker_release"):
        alerts.append("RELEASE_REVISION_MISMATCH")
    if metrics.get("migration_revision") != "0010_wp06_governance":
        alerts.append("MIGRATION_REVISION_MISMATCH")
    return alerts


def http_request(
    path: str, *, method: str = "GET", role: str | None = None,
    body: dict[str, Any] | None = None, idempotency_key: str | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    headers = {"Accept": "application/json"}
    if role is not None:
        headers["X-Fixture-Role"] = role
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    data = None
    if body is not None:
        data = canonical_json(body)
        headers["Content-Type"] = "application/json"
    api_port = int(os.environ.get("MJ_API_PORT", "8000"))
    if not 1 <= api_port <= 65535:
        raise OpsError("MJ_API_PORT must be a valid TCP port")
    request = urllib.request.Request(
        f"http://127.0.0.1:{api_port}{path}", data=data, headers=headers, method=method
    )
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        payload = json.loads(error.read())
        return error.code, payload, {key.lower(): value for key, value in error.headers.items()}
    with response:
        payload = json.loads(response.read())
        return response.status, payload, {key.lower(): value for key, value in response.headers.items()}


def http_negative_check() -> Path:
    status, listed, headers = http_request("/api/v1/ops/enrollments", role="OPERATOR")
    if status != 200 or not listed.get("data", {}).get("items"):
        raise OpsError("operator enrollment fixture is unavailable")
    enrollment = listed["data"]["items"][0]
    enrollment_id = enrollment["id"]
    body = {
        "expected_revision": enrollment["revision"],
        "reviewer_id": enrollment["reviewer_id"],
        "reason": "WP-06 HTTP negative permission check only; no write is authorized.",
    }
    checks: dict[str, dict[str, Any]] = {}

    def expect(
        name: str, expected_status: int, path: str, *, method: str = "GET",
        role: str | None = None, request_body: dict[str, Any] | None = None,
        idempotency_key: str | None = None, expected_code: str | None = None,
    ) -> None:
        actual, payload, response_headers = http_request(
            path, method=method, role=role, body=request_body,
            idempotency_key=idempotency_key,
        )
        code = payload.get("error", {}).get("code")
        if actual != expected_status or (expected_code is not None and code != expected_code):
            raise OpsError(f"HTTP negative check {name} expected {expected_status}/{expected_code}, got {actual}/{code}")
        checks[name] = {
            "status": actual,
            "error_code": code,
            "cache_control": response_headers.get("cache-control"),
        }

    expect("unauthenticated_ops", 401, "/api/v1/ops/enrollments", expected_code="UNAUTHENTICATED")
    expect(
        "learner_cannot_list_ops", 403, "/api/v1/ops/enrollments",
        role="LEARNER", expected_code="FORBIDDEN",
    )
    expect(
        "reviewer_cannot_read_runtime", 403, "/api/v1/ops/runtime-status",
        role="REVIEWER", expected_code="FORBIDDEN",
    )
    expect(
        "missing_idempotency_key", 422,
        f"/api/v1/ops/enrollments/{enrollment_id}/reviewer", method="PUT",
        role="OPERATOR", request_body=body, expected_code="VALIDATION_FAILED",
    )
    expect(
        "wrong_role_cannot_mutate", 403,
        f"/api/v1/ops/enrollments/{enrollment_id}/reviewer", method="PUT",
        role="LEARNER", request_body=body, idempotency_key="wp06-negative-role",
        expected_code="FORBIDDEN",
    )
    expect(
        "cross_org_hidden", 404,
        "/api/v1/ops/enrollments/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/cancel",
        method="POST", role="OPERATOR",
        request_body={"expected_revision": 1, "reason": "跨组织或未知对象必须隐藏存在性并拒绝写入。"},
        idempotency_key="wp06-negative-scope", expected_code="NOT_FOUND",
    )
    query = urllib.parse.urlencode(
        {
            "occurred_after": "2026-01-01T00:00:00Z",
            "occurred_before": "2026-03-01T00:00:00Z",
        }
    )
    expect(
        "audit_range_bounded", 400, f"/api/v1/ops/audit?{query}",
        role="OPERATOR", expected_code="INVALID_REQUEST",
    )
    if headers.get("cache-control") != "no-store" or headers.get("x-content-type-options") != "nosniff":
        raise OpsError("protected response security headers are incomplete")
    directory = make_run_directory()
    report = directory / "http-negative-report.json"
    write_private_json(
        report,
        {
                "schema_version": 1,
                "completed_at": utc_now().isoformat(),
                "scope": "LOCAL_COMPOSE_HTTP",
                "status": "PASS",
                "checks": checks,
                "successful_mutations_executed": False,
        },
    )
    return report


def alert_simulation() -> Path:
    scenarios = {
        "healthy": {
            "worker_stale": False,
            "outbox_backlog": 0,
            "notification_dead": 0,
            "api_release": "candidate",
            "worker_release": "candidate",
            "migration_revision": "0010_wp06_governance",
        },
        "worker_and_queue_failure": {
            "worker_stale": True,
            "outbox_backlog": 10,
            "notification_dead": 1,
            "api_release": "candidate",
            "worker_release": "previous",
            "migration_revision": "0009_notification_scope",
        },
    }
    decisions = {name: alert_decisions(metrics) for name, metrics in scenarios.items()}
    expected = {
        "healthy": [],
        "worker_and_queue_failure": [
            "WORKER_STALE",
            "OUTBOX_BACKLOG_HIGH",
            "NOTIFICATION_DEAD",
            "RELEASE_REVISION_MISMATCH",
            "MIGRATION_REVISION_MISMATCH",
        ],
    }
    if decisions != expected:
        raise OpsError("alert simulation did not produce the expected fail-closed decisions")
    directory = make_run_directory()
    path = directory / "alert-simulation-report.json"
    write_private_json(
        path,
        {
                "schema_version": 1,
                "completed_at": utc_now().isoformat(),
                "scope": "SYNTHETIC_LOCAL_ONLY",
                "status": "PASS",
                "scenarios": scenarios,
                "decisions": decisions,
                "external_alert_delivery": "NOT_RUN",
        },
    )
    return path


def evaluate_release_gate(document: dict[str, Any]) -> dict[str, Any]:
    checks = document.get("checks")
    if document.get("schema_version") != 1 or not isinstance(checks, dict):
        raise OpsError("release gate evidence must use strict schema_version 1")
    unknown = sorted(set(checks) - set(REQUIRED_RELEASE_CHECKS))
    if unknown:
        raise OpsError(f"unknown release checks: {', '.join(unknown)}")
    normalized: dict[str, str] = {}
    for name in REQUIRED_RELEASE_CHECKS:
        value = checks.get(name, "NOT_RUN")
        if value not in ALLOWED_STATUSES:
            raise OpsError(f"invalid status for {name}: {value}")
        normalized[name] = value
    blockers = [name for name, status in normalized.items() if status != "PASS"]
    return {
        "schema_version": 1,
        "candidate": str(document.get("candidate", "UNSPECIFIED")),
        "decision": "NO_GO" if blockers else "GO",
        "blockers": blockers,
        "checks": normalized,
    }


def release_gate(path: Path, expect_no_go: bool) -> int:
    decision = evaluate_release_gate(json.loads(path.read_text()))
    if expect_no_go and not EXTERNAL_BLOCKERS.issubset(set(decision["blockers"])):
        raise OpsError("mandatory human/external/physical blockers were not preserved")
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    if expect_no_go:
        return 0 if decision["decision"] == "NO_GO" else 4
    return 0 if decision["decision"] == "GO" else 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup")
    commands.add_parser("migration-check")
    commands.add_parser("http-negative")
    drill_parser = commands.add_parser("drill")
    drill_source = drill_parser.add_mutually_exclusive_group(required=True)
    drill_source.add_argument("--manifest", type=Path)
    drill_source.add_argument("--latest", action="store_true")
    commands.add_parser("alert-sim")
    gate_parser = commands.add_parser("release-gate")
    gate_parser.add_argument("evidence", type=Path)
    gate_parser.add_argument("--expect-no-go", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "backup":
            print(backup())
            return 0
        if args.command == "migration-check":
            print(migration_check())
            return 0
        if args.command == "http-negative":
            print(http_negative_check())
            return 0
        if args.command == "drill":
            print(drill(latest_manifest() if args.latest else args.manifest.resolve()))
            return 0
        if args.command == "alert-sim":
            print(alert_simulation())
            return 0
        if args.command == "release-gate":
            return release_gate(args.evidence.resolve(), args.expect_no_go)
    except (OpsError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"WP06_OPS_ERROR: {error}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
