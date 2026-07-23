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
WORKFLOW = ROOT / ".github" / "workflows" / "staging.yml"
INFRA_MAIN = ROOT / "infra" / "staging" / "main.tf"
INFRA_VERSIONS = ROOT / "infra" / "staging" / "versions.tf"
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
    if data["monthly_budget_cny"] != 800:
        raise StagingError("WP-08 budget must be exactly CNY 800")
    if not FULL_SHA.fullmatch(str(data["candidate_commit"])):
        raise StagingError("candidate_commit must be one full lowercase SHA")
    origin = urlparse(str(data["staging_origin"]))
    if origin.scheme != "https" or origin.netloc != "staging-vnext.muchenai.com" or origin.path:
        raise StagingError("unexpected staging origin")
    if data["resource_prefix"] != "journey-next-staging":
        raise StagingError("unexpected resource prefix")
    latest_cost = data.get("latest_cost_evidence")
    if latest_cost is not None:
        if not isinstance(latest_cost, dict):
            raise StagingError("latest_cost_evidence must be an object")
        status = latest_cost.get("status")
        if status not in {
            "OVER_BUDGET_NO_DEPLOY",
            "BASELINE_WITHIN_BUDGET_QUOTE_REFRESH_REQUIRED",
            "WITHIN_BUDGET_APPROVED",
        }:
            raise StagingError("latest cost evidence has an unsupported status")
        subtotal = latest_cost.get(
            "subtotal_before_tos_and_traffic_cny",
            latest_cost.get("subtotal_before_tos_backup_and_traffic_cny"),
        )
        if isinstance(subtotal, bool) or not isinstance(subtotal, (int, float)):
            raise StagingError("latest cost subtotal must be numeric")
        if status == "OVER_BUDGET_NO_DEPLOY":
            if subtotal <= data["monthly_budget_cny"]:
                raise StagingError("over-budget evidence must exceed the authorized ceiling")
            if data["approved_monthly_estimate_cny"] is not None:
                raise StagingError("an over-budget quote cannot be approved for apply")
        elif status == "BASELINE_WITHIN_BUDGET_QUOTE_REFRESH_REQUIRED":
            if subtotal > data["monthly_budget_cny"]:
                raise StagingError("within-budget baseline exceeds the authorized ceiling")
            if data["approved_monthly_estimate_cny"] is not None:
                raise StagingError("quote-refresh baseline cannot be approved for apply")
        else:
            forecast = latest_cost.get("approved_monthly_forecast_cny")
            if isinstance(forecast, bool) or not isinstance(forecast, (int, float)):
                raise StagingError("approved monthly forecast must be numeric")
            if forecast < subtotal or forecast > data["monthly_budget_cny"]:
                raise StagingError("approved monthly forecast is outside the budget contract")
            if data["approved_monthly_estimate_cny"] != forecast:
                raise StagingError("approved estimate and latest cost forecast differ")
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
        "scripts/wp08_plan_guard.py",
        "scripts/wp08_dns_record.py",
        "scripts/wp08_security_group.py",
    ]
    for relative in required:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise StagingError(f"required regular file missing: {relative}")
    mode = stat.S_IMODE((ROOT / "deploy/staging/deploy.sh").stat().st_mode)
    if mode != 0o755:
        raise StagingError("deploy/staging/deploy.sh must be mode 0755")


def validate_infrastructure() -> None:
    versions = INFRA_VERSIONS.read_text()
    main = INFRA_MAIN.read_text()
    required_versions = ('source  = "hashicorp/random"', 'version = "3.7.2"')
    for marker in required_versions:
        if marker not in versions:
            raise StagingError(f"staging providers are missing bootstrap marker: {marker}")
    required_main = (
        'resource "random_password" "ecs_bootstrap"',
        'length           = 30',
        'override_special = "!@#%^&*_-+=?"',
        'password                  = random_password.ecs_bootstrap.result',
        'PasswordAuthentication no',
        'KbdInteractiveAuthentication no',
        'PermitRootLogin prohibit-password',
        'stopped_mode              = "KeepCharging"',
        "prevent_destroy = true",
        "depends_on = [volcenginecc_rdspostgresql_instance_ssl.staging]",
        "depends_on = [volcenginecc_rdspostgresql_db_account.migration]",
    )
    for marker in required_main:
        if marker not in main:
            raise StagingError(f"staging infrastructure is missing bootstrap marker: {marker}")
    if main.count("random_password.ecs_bootstrap.result") != 1:
        raise StagingError("ECS bootstrap password must have exactly one non-output consumer")
    if "key_pair_name" in main.lower():
        raise StagingError("staging ECS must not depend on an account-level KeyPair")
    if main.count(
        "depends_on = [volcenginecc_rdspostgresql_instance_ssl.staging]"
    ) != 1:
        raise StagingError("migration account must wait for the RDS SSL mutation")
    if main.count(
        "depends_on = [volcenginecc_rdspostgresql_db_account.migration]"
    ) != 1:
        raise StagingError("runtime account must wait for the migration account mutation")
    ecs_start = main.find('resource "volcenginecc_ecs_instance" "app"')
    ecs_end = main.find('\nresource "', ecs_start + 1)
    if ecs_start < 0:
        raise StagingError("staging ECS resource is missing")
    ecs = main[ecs_start : ecs_end if ecs_end >= 0 else None]
    ignore_match = re.search(r"ignore_changes\s*=\s*\[(.*?)\]", ecs, re.DOTALL)
    if ignore_match is None:
        raise StagingError("staging ECS creation-only ignore list is missing")
    ignored = {
        line.strip().rstrip(",")
        for line in ignore_match.group(1).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    expected_ignored = {
        "eip_address.bandwidth_mbps",
        "eip_address.charge_type",
        "eip_address.isp",
        "eip_address.release_with_instance",
        "image.security_enhancement_strategy",
        "install_run_command_agent",
        "password",
        "system_volume.delete_with_instance",
        "system_volume.size",
        "system_volume.volume_type",
        "user_data",
    }
    if ignored != expected_ignored:
        raise StagingError("staging ECS creation-only ignore list differs from the reviewed set")
    allowlist_start = main.find('resource "volcenginecc_rdspostgresql_allow_list" "app"')
    allowlist_end = main.find('\nresource "', allowlist_start + 1)
    if allowlist_start < 0 or allowlist_end < 0:
        raise StagingError("staging RDS allowlist resource is missing")
    allowlist = main[allowlist_start:allowlist_end]
    if re.search(r"\bip_list\s*=", allowlist):
        raise StagingError("AssociateEcsIp allowlist binding must not configure ip_list")
    if not re.search(
        r"ignore_changes\s*=\s*\[\s*security_group_bind_infos\s*\]", allowlist
    ):
        raise StagingError(
            "AssociateEcsIp nested binding must be immutable after creation"
        )


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
            latest_cost = data.get("latest_cost_evidence")
            if isinstance(latest_cost, dict) and latest_cost.get("status") == "OVER_BUDGET_NO_DEPLOY":
                raise StagingError(
                    "latest official quote exceeds the authorized budget; new authorization is required"
                )
            if (
                isinstance(latest_cost, dict)
                and latest_cost.get("status")
                == "BASELINE_WITHIN_BUDGET_QUOTE_REFRESH_REQUIRED"
            ):
                raise StagingError(
                    "same-day total quote must be refreshed after budget reauthorization"
                )
            raise StagingError("same-day official monthly estimate is not recorded")
        return
    if isinstance(estimate, bool) or not isinstance(estimate, (int, float)):
        raise StagingError("approved monthly estimate must be numeric or null")
    if estimate <= 0 or estimate > data["monthly_budget_cny"]:
        raise StagingError("approved monthly estimate exceeds the authorized budget")


def check(phase: str) -> None:
    data = load_contract()
    validate_files()
    validate_infrastructure()
    validate_candidate(data)
    validate_cost(data, require_quote=phase == "apply")
    print(
        "WP08_STAGING_CONTRACT=PASS"
        f" phase={phase} candidate={data['candidate_commit']}"
        f" region={data['region_id']} budget_cny={data['monthly_budget_cny']}"
        f" estimate_cny={data['approved_monthly_estimate_cny']}"
    )


def validate_workflow(path: Path = WORKFLOW) -> None:
    validate_infrastructure()
    workflow = path.read_text()
    required = (
        "- provision\n          - deploy",
        "id: terraform_init",
        "if: inputs.phase == 'provision'",
        "id: frozen_infrastructure",
        "terraform output -raw staging_public_ip",
        "if: always() && inputs.phase == 'deploy' && steps.frozen_infrastructure.outputs.security_group_id != ''",
        "terraform show -json",
        "scripts/wp08_plan_guard.py",
        "scripts/wp08_dns_record.py",
        "scripts.wp08_security_group open",
        "scripts.wp08_security_group close",
        'terraform import "$address" "$expected_id"',
        "terraform state pull | jq -er",
        'terraform apply -auto-approve "$plan_file"',
        '-var="deploy_cidr=127.0.0.1/32"',
    )
    for marker in required:
        if marker not in workflow:
            raise StagingError(f"staging workflow is missing bootstrap marker: {marker}")
    if workflow.count("if: inputs.phase == 'deploy'") != 5:
        raise StagingError("staging workflow deploy-only step count must be exactly 5")
    if workflow.count("if: inputs.phase == 'provision'") != 2:
        raise StagingError("staging workflow provision-only step count must be exactly 2")
    if workflow.count("scripts/wp08_plan_guard.py") != 1:
        raise StagingError("every WP-08 apply path must have one destructive-plan guard")
    if workflow.count("scripts/wp08_dns_record.py") != 1:
        raise StagingError("WP-08 must identify the existing DNS record exactly once")
    if workflow.count('terraform import "$address" "$expected_id"') != 1:
        raise StagingError("WP-08 DNS reconciliation must have exactly one import path")
    if workflow.count("terraform state pull | jq -er") != 1:
        raise StagingError("WP-08 must verify the existing DNS state identity exactly once")
    if workflow.count("scripts.wp08_security_group") != 2:
        raise StagingError("WP-08 must directly open and close one exact SSH rule")
    if "-target=volcenginecc_vpc_security_group.app" in workflow:
        raise StagingError("WP-08 must not update the nested security group rule set")
    if "terraform apply -auto-approve -var=" in workflow:
        raise StagingError("WP-08 apply must consume a reviewed and guarded saved plan")
    guard_positions = [
        match.start() for match in re.finditer(r"scripts/wp08_plan_guard\.py", workflow)
    ]
    apply_positions = [match.start() for match in re.finditer(r"terraform apply", workflow)]
    if len(apply_positions) != 1 or guard_positions[0] > apply_positions[0]:
        raise StagingError("WP-08 destructive-plan guard must run before every apply")
    apply_step_start = workflow.find("- name: Apply reviewed infrastructure")
    apply_step_end = workflow.find("\n      - name:", apply_step_start + 1)
    if apply_step_start < 0 or apply_step_end < 0:
        raise StagingError("staging provision step is missing")
    apply_step = workflow[apply_step_start:apply_step_end]
    if "if: inputs.phase == 'provision'" not in apply_step:
        raise StagingError("Terraform apply must be provision-only")
    frozen_step_start = workflow.find("- name: Read frozen Alpha pilot infrastructure")
    frozen_step_end = workflow.find("\n      - name:", frozen_step_start + 1)
    if frozen_step_start < 0 or frozen_step_end < 0:
        raise StagingError("frozen Alpha pilot state reader is missing")
    frozen_step = workflow[frozen_step_start:frozen_step_end]
    for forbidden in ("terraform plan", "terraform apply", "terraform import", "wp08_dns_record.py"):
        if forbidden in frozen_step:
            raise StagingError("Alpha pilot deploy must not reconcile infrastructure")
    print("WP08_STAGING_WORKFLOW=PASS phases=provision,frozen-alpha-deploy")


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
    subparsers.add_parser("workflow-check")
    evidence_parser = subparsers.add_parser("record")
    evidence_parser.add_argument("--status", required=True)
    evidence_parser.add_argument("--reference", required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            check(args.phase)
        elif args.command == "workflow-check":
            validate_workflow()
        else:
            record_evidence(args.status, args.reference)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, StagingError) as error:
        print(f"WP08_STAGING_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
