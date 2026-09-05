import json
import uuid
from pathlib import Path

import pytest

from scripts import wp31_identity_bootstrap as bootstrap


def _request(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "operator_user_id": str(uuid.uuid4()),
        "operator_display_name": "许瀚文",
        "learner_user_id": str(uuid.uuid4()),
        "learner_display_name": "组长",
        "owner_user_id": str(uuid.uuid4()),
        "owner_display_name": "刘默文",
        "authorization_reference": "IDENTITY-BOOTSTRAP-20260904",
        "expires_in_minutes": 15,
    }
    value.update(overrides)
    return value


def test_request_parser_accepts_exact_non_sensitive_shape(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(_request(), ensure_ascii=False) + "\n", encoding="utf-8")

    parsed = bootstrap.parse_request(path)

    assert parsed.operator_display_name == "许瀚文"
    assert parsed.learner_display_name == "组长"
    assert parsed.expires_in_minutes == 15
    assert parsed.operator_user_id.version == 4
    assert parsed.learner_user_id.version == 4


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("unexpected", "secret", "fields differ"),
        ("operator_user_id", "not-a-uuid", "UUIDv4"),
        ("operator_display_name", "bad\nname", "display name"),
        ("learner_display_name", "许瀚文", "must differ"),
        ("owner_display_name", "许瀚文", "must differ"),
        ("authorization_reference", "token value", "authorization reference"),
        ("expires_in_minutes", 31, "5-30"),
    ],
)
def test_request_parser_rejects_unsafe_or_ambiguous_input(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    payload = _request()
    payload[field] = value
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(bootstrap.BootstrapError, match=message):
        bootstrap.parse_request(path)


def test_request_parser_rejects_same_user_id() -> None:
    user_id = str(uuid.uuid4())
    with pytest.raises(bootstrap.BootstrapError, match="must differ"):
        bootstrap.parse_payload(_request(learner_user_id=user_id, operator_user_id=user_id))


def test_request_parser_rejects_owner_id_collision() -> None:
    user_id = str(uuid.uuid4())
    with pytest.raises(bootstrap.BootstrapError, match="must differ"):
        bootstrap.parse_payload(_request(owner_user_id=user_id, learner_user_id=user_id))


def test_runtime_guard_allows_only_exact_isolated_canary_and_tls() -> None:
    valid = (
        "postgresql+psycopg://journey_next_migrator:pw@"
        "private.rds.example:5432/journey_next_cutover_20260810"
        "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
    )
    with pytest.raises(bootstrap.BootstrapError, match="Canary database"):
        bootstrap.validate_runtime(
            valid,
            app_env="production",
            release_marker="PRODUCTION_CANARY_UAT",
            confirmation=bootstrap.CONFIRMATION,
        )

    target = valid.replace("journey_next_cutover_20260810", "journey_next_canary_20260901_c72fea5")
    assert bootstrap.validate_runtime(
        target,
        app_env="production",
        release_marker="PRODUCTION_CANARY_UAT",
        confirmation=bootstrap.CONFIRMATION,
        database_kind="canary",
    ) is None

    target = valid.replace("journey_next_cutover_20260810", "journey_next_canary_20260901_c72fea5")
    for database_url, message in [
        (valid.replace("journey_next_cutover_20260810", "journey_next_dev"), "Canary database"),
        (target.replace("sslmode=verify-full", "sslmode=require"), "verify-full"),
        (target.replace("private.rds.example", "localhost"), "host"),
        (target.replace("journey_next_migrator", "journey_next_runtime"), "credentials"),
        (target.replace("/run/secrets/volcengine-rds-ca.pem", "/tmp/ca.pem"), "CA path"),
    ]:
        with pytest.raises(bootstrap.BootstrapError, match=message):
            bootstrap.validate_runtime(
                database_url,
                app_env="production",
                release_marker="PRODUCTION_CANARY_UAT",
                confirmation=bootstrap.CONFIRMATION,
                database_kind="canary",
            )


def test_public_result_contains_ids_and_link_but_never_display_names() -> None:
    result = bootstrap.public_result(
        {
            "operator_user_id": "operator",
            "learner_user_id": "learner",
            "owner_user_id": "owner",
            "operator_roles": ["OPERATOR", "REVIEWER"],
            "owner_roles": ["LEARNER", "REVIEWER"],
            "operator_link_id": "link",
            "operator_link_start_path": "/auth/feishu?link_token=opaque",
            "operator_link_expires_at": "2026-09-04T12:15:00+00:00",
            "expires_in_minutes": 15,
            "operator_display_name": "许瀚文",
            "learner_display_name": "组长",
            "owner_display_name": "刘默文",
        }
    )

    assert result["operator_user_id"] == "operator"
    assert result["owner_user_id"] == "owner"
    assert result["owner_roles"] == ["LEARNER", "REVIEWER"]
    assert "operator_display_name" not in result
    assert "learner_display_name" not in result
    assert "owner_display_name" not in result
    assert "组长" not in json.dumps(result, ensure_ascii=False)
    assert "刘默文" not in json.dumps(result, ensure_ascii=False)


def test_workflow_has_one_fast_canary_path_and_no_source_database_identity_job() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/wp15-wartime-production.yml").read_text(encoding="utf-8")
    assert "greenfield-canary-fast" in workflow
    assert "FAST_CANARY_0E86352_PRODUCTION_CANARY" in workflow
    assert "--database-kind canary" in workflow
    assert "greenfield_identity_bootstrap:" not in workflow
    assert "greenfield-identity-bootstrap" not in workflow
    fast_job = workflow[workflow.index("  greenfield_canary:\n") : workflow.index("  operate:\n")]
    assert "inputs.phase == 'greenfield-canary-fast'" in fast_job
    assert "Create only the exact isolated canary database" in fast_job
    assert "Deploy exact zero-worker Canary" in fast_job
    assert "owner_user_id" in fast_job
    assert 'value["owner_roles"] == ["LEARNER","REVIEWER"]' in fast_job
    assert "Download exact preflight evidence before infrastructure access" in workflow
    assert "if: inputs.phase == 'greenfield-backup-restore' || inputs.phase == 'greenfield-deploy'" in workflow
