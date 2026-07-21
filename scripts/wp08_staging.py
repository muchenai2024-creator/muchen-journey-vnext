#!/usr/bin/env python3
"""Fail-closed WP-08 staging contract and private evidence helper."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "wp08_staging.json"
PRIVATE_EVIDENCE = ROOT / "evidence" / "private" / "wp08"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class StagingError(RuntimeError):
    pass


def load_contract(path: Path = CONTRACT) -> dict[str, object]:
    data = json.loads(path.read_text())
    required = {
        "provider",
        "region_id",
        "billing_mode",
        "monthly_budget_cny",
        "approved_monthly_estimate_cny",
        "candidate_commit",
        "staging_origin",
        "resource_prefix",
    }
    missing = required - data.keys()
    if missing:
        raise StagingError(f"contract missing keys: {','.join(sorted(missing))}")
    if data["provider"] != "volcengine":
        raise StagingError("WP-08 provider must be volcengine")
    if data["region_id"] != "cn-beijing":
        raise StagingError("WP-08 region must be cn-beijing")
    if data["billing_mode"] != "PostPaid":
        raise StagingError("WP-08 billing must be PostPaid")
    if data["monthly_budget_cny"] != 500:
        raise StagingError("WP-08 budget must be exactly CNY 500")
    if not FULL_SHA.fullmatch(str(data["candidate_commit"])):
        raise StagingError("candidate_commit must be one full lowercase SHA")
    origin = urlparse(str(data["staging_origin"]))
    if origin.scheme != "https" or origin.netloc != "staging-vnext.muchenai.com" or origin.path:
        raise StagingError("unexpected staging origin")
    if data["resource_prefix"] != "journey-next-staging":
        raise StagingError("unexpected resource prefix")
    return data


def validate_files() -> None:
    required = [
        "infra/staging/versions.tf",
        "infra/staging/variables.tf",
        "infra/staging/main.tf",
        "infra/staging/outputs.tf",
        "deploy/staging/compose.yaml",
        "deploy/staging/compose.migrate.yaml",
        "deploy/staging/Caddyfile",
        "deploy/staging/grant_runtime.py",
        "deploy/staging/deploy.sh",
    ]
    for relative in required:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise StagingError(f"required regular file missing: {relative}")
    mode = stat.S_IMODE((ROOT / "deploy/staging/deploy.sh").stat().st_mode)
    if mode != 0o755:
        raise StagingError("deploy/staging/deploy.sh must be mode 0755")


def validate_candidate(data: dict[str, object]) -> None:
    manifest_path = ROOT / "artifacts" / "wp07-candidate" / "release-manifest.json"
    if not manifest_path.is_file():
        raise StagingError("local canonical WP-07 candidate manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    candidate = manifest.get("candidate", {})
    if candidate.get("commit_sha") != data["candidate_commit"]:
        raise StagingError("WP-08 contract and WP-07 candidate manifest differ")
    external = manifest.get("external_status", {})
    if external.get("registry_push") != "VERIFIED":
        raise StagingError("candidate registry push is not VERIFIED")
    if external.get("deployment") != "NOT_RUN":
        raise StagingError("candidate deployment must remain NOT_RUN before WP-08 apply")


def validate_cost(data: dict[str, object], *, require_quote: bool) -> None:
    estimate = data["approved_monthly_estimate_cny"]
    if estimate is None:
        if require_quote:
            raise StagingError("same-day official monthly estimate is not recorded")
        return
    if isinstance(estimate, bool) or not isinstance(estimate, (int, float)):
        raise StagingError("approved monthly estimate must be numeric or null")
    if estimate <= 0 or estimate > data["monthly_budget_cny"]:
        raise StagingError("approved monthly estimate exceeds the authorized budget")


def check(phase: str) -> None:
    data = load_contract()
    validate_files()
    validate_candidate(data)
    validate_cost(data, require_quote=phase == "apply")
    print(
        "WP08_STAGING_CONTRACT=PASS"
        f" phase={phase} candidate={data['candidate_commit']}"
        f" region={data['region_id']} budget_cny={data['monthly_budget_cny']}"
        f" estimate_cny={data['approved_monthly_estimate_cny']}"
    )


def command_output(*args: str) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def record_evidence(status: str, reference: str) -> None:
    if status not in {"APPLIED", "DEPLOYED", "VERIFIED", "FAILED"}:
        raise StagingError("unsupported evidence status")
    if not re.fullmatch(r"[A-Z0-9_-]{3,80}", reference):
        raise StagingError("reference must be one non-sensitive identifier")
    data = load_contract()
    PRIVATE_EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE_EVIDENCE.chmod(0o700)
    payload = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "candidate_commit": data["candidate_commit"],
        "repository_head": command_output("git", "rev-parse", "HEAD"),
        "region_id": data["region_id"],
        "staging_origin": data["staging_origin"],
        "status": status,
        "reference": reference,
        "contains_pii": False,
        "contains_secrets": False,
    }
    target = PRIVATE_EVIDENCE / f"physical-{status.lower()}.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(target)
    target.chmod(0o600)
    print(f"WP08_PRIVATE_EVIDENCE={target.relative_to(ROOT)} status={status}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--phase", choices=("readiness", "apply"), required=True)
    evidence_parser = subparsers.add_parser("record")
    evidence_parser.add_argument("--status", required=True)
    evidence_parser.add_argument("--reference", required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            check(args.phase)
        else:
            record_evidence(args.status, args.reference)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, StagingError) as error:
        print(f"WP08_STAGING_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
