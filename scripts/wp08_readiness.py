#!/usr/bin/env python3
"""Fail-closed, provider-neutral WP-08 Definition of Ready checks.

The commands in this module only inspect repository/local Docker state or write
to ignored local evidence paths. They do not create cloud resources, domains,
secrets, ACLs, GitHub environments, or staging deployments.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.journey_api.fixtures import FIXTURE_MANIFEST  # noqa: E402
from scripts.wp07_candidate import migration  # noqa: E402


DEFAULT_BROWSER_SPEC = ROOT / "config" / "wp08_browser_smoke.json"
DEFAULT_PRIVATE_ROOT = ROOT / "evidence" / "private" / "wp08"
PRIVATE_METADATA_NAME = "boundary.json"
UTC = timezone.utc


class ReadinessError(RuntimeError):
    """Expected fail-closed readiness error."""


def run(arguments: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(arguments),
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise ReadinessError(f"{arguments[0]} failed: {detail}")
    return result


def write_json(path: Path, value: Any, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if private:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.chmod(path, 0o600)
    else:
        path.write_text(payload, encoding="utf-8")


def fixture_manifest(output: Path) -> dict[str, Any]:
    manifest = json.loads(json.dumps(FIXTURE_MANIFEST))
    if manifest.get("classification") != "SYNTHETIC_NO_REAL_PII":
        raise ReadinessError("fixture manifest must explicitly exclude real PII")
    if manifest.get("builder") != "python -m journey_api.seed":
        raise ReadinessError("fixture manifest must use the canonical seed builder")
    if not manifest.get("tables") or not manifest.get("stable_references"):
        raise ReadinessError("fixture manifest must list tables, fields, and stable references")
    forbidden = {"token", "email", "phone", "submission_body", "feedback_body", "bytes"}
    fields = {
        field
        for table_fields in manifest["tables"].values()
        for field in table_fields
    }
    leaked = sorted(fields & forbidden)
    if leaked:
        raise ReadinessError(f"fixture manifest exposes prohibited value fields: {leaked}")
    write_json(output.resolve(), manifest)
    return manifest


def browser_spec(path: Path) -> dict[str, Any]:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReadinessError(f"browser spec is unavailable or invalid: {error}") from error
    if spec.get("browser") != "chromium" or spec.get("browser_revision") != "1232":
        raise ReadinessError("browser spec must pin Chromium revision 1232")
    if spec.get("evidence_directory") != "output/playwright/wp08":
        raise ReadinessError("browser evidence directory must be canonical")
    expected = {
        ("desktop", 1440, 900),
        ("tablet", 768, 1024),
        ("mobile", 390, 844),
    }
    actual = {
        (item.get("name"), item.get("width"), item.get("height"))
        for item in spec.get("viewports", [])
    }
    if actual != expected:
        raise ReadinessError("browser spec must contain the three canonical viewports")
    required_checks = {"http_status", "console_error", "horizontal_overflow", "focus_keyboard"}
    if set(spec.get("checks", [])) != required_checks:
        raise ReadinessError("browser spec is missing a canonical smoke check")
    return spec


def browser_preflight(spec_path: Path) -> dict[str, Any]:
    spec = browser_spec(spec_path)
    if shutil.which("npx") is None:
        raise ReadinessError("npx is required by the Playwright CLI wrapper")
    cli_value = os.environ.get("PLAYWRIGHT_CLI", "")
    browser_value = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "")
    base_url = os.environ.get("BROWSER_BASE_URL", "")
    scope = os.environ.get("BROWSER_SCOPE", "local")
    if not cli_value or not browser_value or not base_url:
        raise ReadinessError(
            "PLAYWRIGHT_CLI, PLAYWRIGHT_CHROMIUM_EXECUTABLE, and BROWSER_BASE_URL are required"
        )
    cli = Path(cli_value).expanduser().resolve()
    executable = Path(browser_value).expanduser().resolve()
    if not cli.is_file():
        raise ReadinessError("PLAYWRIGHT_CLI must resolve to a file")
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ReadinessError("PLAYWRIGHT_CHROMIUM_EXECUTABLE must be an executable file")
    if f"chromium-{spec['browser_revision']}" not in executable.as_posix():
        raise ReadinessError("Chromium executable does not match the pinned revision")
    parsed = urlparse(base_url)
    local_hosts = {"localhost", "127.0.0.1"}
    if scope == "local":
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in local_hosts:
            raise ReadinessError("local browser scope requires an explicit localhost URL")
    elif scope == "staging":
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname in local_hosts:
            raise ReadinessError("staging browser scope requires a non-local HTTPS URL")
    else:
        raise ReadinessError("BROWSER_SCOPE must be local or staging")
    ignored = run(("git", "check-ignore", "-q", spec["evidence_directory"]), check=False)
    if ignored.returncode != 0:
        raise ReadinessError("browser evidence directory must be ignored by Public Git")
    return {
        "status": "PASS",
        "scope": scope,
        "base_url": base_url,
        "browser_revision": spec["browser_revision"],
        "evidence_directory": spec["evidence_directory"],
    }


def cold_preflight() -> dict[str, Any]:
    required = ("docker", "git", "python3", "node", "npm", "npx")
    missing = [command for command in required if shutil.which(command) is None]
    if missing:
        raise ReadinessError(f"required tools are missing: {missing}")
    run(("docker", "info", "--format", "{{.ServerVersion}}"))
    run(("docker", "compose", "config", "--quiet"))
    running = run(
        ("docker", "compose", "ps", "--status", "running", "--services")
    ).stdout.split()
    if running:
        raise ReadinessError(f"cold preflight requires stopped project services: {running}")
    return {"status": "PASS", "required_tools": list(required), "project_services": "STOPPED"}


def private_root(value: Path) -> Path:
    requested = value.expanduser()
    if requested.is_symlink():
        raise ReadinessError("private evidence root must not be a symlink")
    root = requested.resolve()
    if root == ROOT or ROOT in root.parents:
        ignored = run(("git", "check-ignore", "-q", str(root)), check=False)
        if ignored.returncode != 0:
            raise ReadinessError("private evidence inside the repository must be Git-ignored")
    return root


def evidence_init(value: Path, retention_days: int) -> Path:
    if retention_days < 30 or retention_days > 365:
        raise ReadinessError("private evidence retention must be between 30 and 365 days")
    root = private_root(value)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    metadata = root / PRIVATE_METADATA_NAME
    if metadata.is_symlink():
        raise ReadinessError("private evidence metadata must not be a symlink")
    write_json(
        metadata,
        {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "owner": getpass.getuser(),
            "access_scope": "LOCAL_FILESYSTEM_OWNER_ONLY",
            "retention_days": retention_days,
            "public_reference_format": "PEV-WP08-YYYYMMDD-<NON_SECRET_ID>",
            "prohibited_public_data": [
                "real_person_or_roster",
                "tenant_or_app_id",
                "unpublished_domain_or_ip",
                "acl_detail_or_secret",
                "runtime_screenshot_or_business_data",
            ],
        },
        private=True,
    )
    return metadata


def evidence_check(value: Path) -> dict[str, Any]:
    root = private_root(value)
    metadata = root / PRIVATE_METADATA_NAME
    if not root.is_dir() or stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise ReadinessError("private evidence root must exist with mode 0700")
    if not metadata.is_file() or stat.S_IMODE(metadata.stat().st_mode) != 0o600:
        raise ReadinessError("private evidence metadata must exist with mode 0600")
    config = json.loads(metadata.read_text(encoding="utf-8"))
    required = {
        "owner",
        "access_scope",
        "retention_days",
        "public_reference_format",
        "prohibited_public_data",
    }
    if not required <= set(config) or config.get("access_scope") != "LOCAL_FILESYSTEM_OWNER_ONLY":
        raise ReadinessError("private evidence boundary metadata is incomplete")
    return {
        "status": "PASS",
        "owner": config["owner"],
        "access_scope": config["access_scope"],
        "retention_days": config["retention_days"],
        "public_reference_format": config["public_reference_format"],
    }


def git_check() -> dict[str, Any]:
    branch = run(("git", "branch", "--show-current")).stdout.strip()
    if not branch.startswith("codex/wp-08-"):
        raise ReadinessError("WP-08 must run on one codex/wp-08-* branch")
    if run(("git", "status", "--porcelain=v1", "--untracked-files=all")).stdout.strip():
        raise ReadinessError("WP-08 readiness requires a clean worktree")
    head = run(("git", "rev-parse", "HEAD")).stdout.strip()
    main = run(("git", "rev-parse", "origin/main")).stdout.strip()
    base = run(("git", "merge-base", "HEAD", "origin/main")).stdout.strip()
    if base != main:
        raise ReadinessError("WP-08 branch must be based on the exact current origin/main")
    return {"status": "PASS", "branch": branch, "head_sha": head, "main_sha": main}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("fixture-manifest")
    manifest.add_argument("--output", type=Path, required=True)
    browser = commands.add_parser("browser-preflight")
    browser.add_argument("--spec", type=Path, default=DEFAULT_BROWSER_SPEC)
    commands.add_parser("cold-preflight")
    evidence = commands.add_parser("evidence-init")
    evidence.add_argument("--root", type=Path, default=DEFAULT_PRIVATE_ROOT)
    evidence.add_argument("--retention-days", type=int, default=90)
    evidence_check_parser = commands.add_parser("evidence-check")
    evidence_check_parser.add_argument("--root", type=Path, default=DEFAULT_PRIVATE_ROOT)
    commands.add_parser("git-check")
    commands.add_parser("migration-static")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "fixture-manifest":
            result: Any = fixture_manifest(args.output)
        elif args.command == "browser-preflight":
            result = browser_preflight(args.spec)
        elif args.command == "cold-preflight":
            result = cold_preflight()
        elif args.command == "evidence-init":
            result = {"private_metadata": str(evidence_init(args.root, args.retention_days))}
        elif args.command == "evidence-check":
            result = evidence_check(args.root)
        elif args.command == "git-check":
            result = git_check()
        elif args.command == "migration-static":
            result = migration()
        else:
            raise AssertionError("unreachable")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (ReadinessError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"WP08_READINESS_ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
