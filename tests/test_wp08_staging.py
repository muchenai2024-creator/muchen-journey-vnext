import json
from pathlib import Path

import pytest

import scripts.wp08_staging as staging


def contract(tmp_path: Path, *, estimate=None) -> Path:
    path = tmp_path / "contract.json"
    path.write_text(
        json.dumps(
            {
                "provider": "volcengine",
                "region_id": "cn-beijing",
                "billing_mode": "PostPaid",
                "monthly_budget_cny": 800,
                "approved_monthly_estimate_cny": estimate,
                "candidate_commit": "f" * 40,
                "staging_origin": "https://staging-vnext.muchenai.com",
                "resource_prefix": "journey-next-staging",
            }
        )
    )
    return path


def infrastructure_files(tmp_path: Path) -> tuple[Path, Path]:
    versions = tmp_path / "versions.tf"
    versions.write_text('source  = "hashicorp/random"\nversion = "3.7.2"\n')
    main = tmp_path / "main.tf"
    main.write_text(
        "\n".join(
            (
                'resource "random_password" "ecs_bootstrap" {',
                'length           = 30',
                'override_special = "!@#%^&*_-+=?"',
                '}',
                'resource "volcenginecc_rdspostgresql_allow_list" "app" {',
                'security_group_bind_infos = [{',
                'bind_mode = "AssociateEcsIp"',
                'security_group_id = "sg-reviewed"',
                'security_group_name = "journey-next-staging-app"',
                '}]',
                'lifecycle {',
                'ignore_changes = [security_group_bind_infos]',
                '}',
                '}',
                'resource "volcenginecc_rdspostgresql_instance_ssl" "staging" {',
                '}',
                'resource "volcenginecc_rdspostgresql_db_account" "migration" {',
                'depends_on = [volcenginecc_rdspostgresql_instance_ssl.staging]',
                '}',
                'resource "volcenginecc_rdspostgresql_db_account" "runtime" {',
                'depends_on = [volcenginecc_rdspostgresql_db_account.migration]',
                '}',
                'resource "volcenginecc_ecs_instance" "app" {',
                'password                  = random_password.ecs_bootstrap.result',
                'PasswordAuthentication no',
                'KbdInteractiveAuthentication no',
                'PermitRootLogin prohibit-password',
                'stopped_mode              = "KeepCharging"',
                'prevent_destroy = true',
                'ignore_changes = [',
                'eip_address.bandwidth_mbps',
                'eip_address.charge_type',
                'eip_address.isp',
                'eip_address.release_with_instance',
                'image.security_enhancement_strategy',
                'install_run_command_agent',
                'password',
                'system_volume.delete_with_instance',
                'system_volume.size',
                'system_volume.volume_type',
                'user_data',
                ']',
                '}',
            )
        )
    )
    return versions, main


def test_contract_locks_provider_region_budget_and_origin(tmp_path: Path):
    data = staging.load_contract(contract(tmp_path))
    assert data["region_id"] == "cn-beijing"
    assert data["monthly_budget_cny"] == 800


def test_apply_requires_quote_and_rejects_over_budget(tmp_path: Path):
    data = staging.load_contract(contract(tmp_path))
    staging.validate_cost(data, require_quote=False)
    with pytest.raises(staging.StagingError, match="estimate is not recorded"):
        staging.validate_cost(data, require_quote=True)

    over = staging.load_contract(contract(tmp_path, estimate=800.01))
    with pytest.raises(staging.StagingError, match="exceeds"):
        staging.validate_cost(over, require_quote=True)


def test_apply_accepts_positive_quote_within_budget(tmp_path: Path):
    data = staging.load_contract(contract(tmp_path, estimate=799.99))
    staging.validate_cost(data, require_quote=True)


def test_over_budget_evidence_preserves_null_approval(tmp_path: Path):
    path = contract(tmp_path)
    payload = json.loads(path.read_text())
    payload["latest_cost_evidence"] = {
        "status": "OVER_BUDGET_NO_DEPLOY",
        "subtotal_before_tos_backup_and_traffic_cny": 800.01,
    }
    path.write_text(json.dumps(payload))
    data = staging.load_contract(path)
    assert data["approved_monthly_estimate_cny"] is None
    with pytest.raises(staging.StagingError, match="quote exceeds"):
        staging.validate_cost(data, require_quote=True)

    payload["approved_monthly_estimate_cny"] = 799
    path.write_text(json.dumps(payload))
    with pytest.raises(staging.StagingError, match="cannot be approved"):
        staging.load_contract(path)


def test_reauthorized_baseline_requires_refreshed_total_quote(tmp_path: Path):
    path = contract(tmp_path)
    payload = json.loads(path.read_text())
    payload["latest_cost_evidence"] = {
        "status": "BASELINE_WITHIN_BUDGET_QUOTE_REFRESH_REQUIRED",
        "subtotal_before_tos_backup_and_traffic_cny": 717.26,
    }
    path.write_text(json.dumps(payload))
    data = staging.load_contract(path)
    with pytest.raises(staging.StagingError, match="quote must be refreshed"):
        staging.validate_cost(data, require_quote=True)

    payload["approved_monthly_estimate_cny"] = 717.26
    path.write_text(json.dumps(payload))
    with pytest.raises(staging.StagingError, match="cannot be approved"):
        staging.load_contract(path)


def test_approved_quote_matches_forecast_and_budget(tmp_path: Path):
    path = contract(tmp_path, estimate=656.26)
    payload = json.loads(path.read_text())
    payload["latest_cost_evidence"] = {
        "status": "WITHIN_BUDGET_APPROVED",
        "subtotal_before_tos_and_traffic_cny": 573.26,
        "approved_monthly_forecast_cny": 656.26,
    }
    path.write_text(json.dumps(payload))
    data = staging.load_contract(path)
    staging.validate_cost(data, require_quote=True)

    payload["approved_monthly_estimate_cny"] = 656.25
    path.write_text(json.dumps(payload))
    with pytest.raises(staging.StagingError, match="forecast differ"):
        staging.load_contract(path)


def test_infrastructure_uses_state_only_bootstrap_password(tmp_path: Path, monkeypatch):
    versions, main = infrastructure_files(tmp_path)
    monkeypatch.setattr(staging, "INFRA_VERSIONS", versions)
    monkeypatch.setattr(staging, "INFRA_MAIN", main)
    staging.validate_infrastructure()

    main.write_text(main.read_text().replace("PasswordAuthentication no", ""))
    with pytest.raises(staging.StagingError, match="bootstrap marker"):
        staging.validate_infrastructure()


def test_infrastructure_rejects_unreviewed_ignore_set_and_mutable_allowlist_binding(
    tmp_path: Path, monkeypatch
):
    versions, main = infrastructure_files(tmp_path)
    source = main.read_text()
    main.write_text(source.replace("user_data\n", ""))
    monkeypatch.setattr(staging, "INFRA_VERSIONS", versions)
    monkeypatch.setattr(staging, "INFRA_MAIN", main)
    with pytest.raises(staging.StagingError, match="ignore list differs"):
        staging.validate_infrastructure()

    main.write_text(source.replace("security_group_name", "ip_list = []\nsecurity_group_name", 1))
    with pytest.raises(staging.StagingError, match="must not configure ip_list"):
        staging.validate_infrastructure()

    main.write_text(source.replace("ignore_changes = [security_group_bind_infos]", ""))
    with pytest.raises(staging.StagingError, match="must be immutable after creation"):
        staging.validate_infrastructure()


def test_workflow_requires_guard_before_each_saved_plan_apply(tmp_path: Path, monkeypatch):
    versions, main = infrastructure_files(tmp_path)
    monkeypatch.setattr(staging, "INFRA_VERSIONS", versions)
    monkeypatch.setattr(staging, "INFRA_MAIN", main)
    workflow = tmp_path / "staging.yml"
    source = "\n".join(
        (
            "- provision",
            "          - deploy",
            "id: terraform_init",
            "      - name: Reconcile the exact existing staging DNS record",
            "        if: inputs.phase == 'provision'",
            "scripts/wp08_dns_record.py",
            'terraform state pull | jq -er',
            'terraform import "$address" "$expected_id"',
            "      - name: Apply reviewed infrastructure",
            "        if: inputs.phase == 'provision'",
            'terraform show -json "$plan_file" | python3 ../../scripts/wp08_plan_guard.py',
            'terraform apply -auto-approve "$plan_file"',
            '-var="deploy_cidr=127.0.0.1/32"',
            "      - name: Read frozen Alpha pilot infrastructure",
            "        if: inputs.phase == 'deploy'",
            "        id: frozen_infrastructure",
            "terraform output -raw staging_public_ip",
            "      - name: Open exact runner SSH ingress",
            "if: inputs.phase == 'deploy'",
            "python3 -m scripts.wp08_security_group open",
            "      - name: Prepare private deploy bundle",
            "if: inputs.phase == 'deploy'",
            "      - name: Deploy exact registry digests",
            "if: inputs.phase == 'deploy'",
            "      - name: Verify external TLS and release surface",
            "if: inputs.phase == 'deploy'",
            "      - name: Close SSH ingress",
            "if: always() && inputs.phase == 'deploy' && steps.frozen_infrastructure.outputs.security_group_id != ''",
            "python3 -m scripts.wp08_security_group close",
        )
    )
    workflow.write_text(source)
    staging.validate_workflow(workflow)

    workflow.write_text(source.replace("scripts/wp08_plan_guard.py", "scripts/missing.py", 1))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(source.replace("scripts.wp08_security_group close", "missing"))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(
        source.replace(
            "terraform output -raw staging_public_ip",
            "terraform output -raw staging_public_ip\nterraform plan",
        )
    )
    with pytest.raises(staging.StagingError, match="must not reconcile"):
        staging.validate_workflow(workflow)


def test_infrastructure_requires_serial_rds_exclusive_operations(
    tmp_path: Path, monkeypatch
):
    versions, main = infrastructure_files(tmp_path)
    monkeypatch.setattr(staging, "INFRA_VERSIONS", versions)
    monkeypatch.setattr(staging, "INFRA_MAIN", main)
    source = main.read_text()

    main.write_text(
        source.replace(
            "depends_on = [volcenginecc_rdspostgresql_instance_ssl.staging]", ""
        )
    )
    with pytest.raises(staging.StagingError, match="bootstrap marker"):
        staging.validate_infrastructure()

    main.write_text(
        source.replace(
            "depends_on = [volcenginecc_rdspostgresql_db_account.migration]", ""
        )
    )
    with pytest.raises(staging.StagingError, match="bootstrap marker"):
        staging.validate_infrastructure()
