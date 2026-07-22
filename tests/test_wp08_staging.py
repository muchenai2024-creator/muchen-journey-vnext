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
