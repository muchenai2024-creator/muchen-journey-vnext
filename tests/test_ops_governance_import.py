import hashlib
import hmac
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from journey_api import offline_import
from journey_api.config import Settings, get_settings
from journey_api.db import SessionLocal
from journey_api.fixtures import (
    OPERATOR_ID,
    ORGANIZATION_ID,
    REVIEWER_ID,
    TASK_DEFINITION_ID,
    TASK_VERSION_ID,
)
from journey_api.main import app
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    AuditEntry,
    Enrollment,
    EnrollmentStatus,
    ImportBatch,
    ImportRecord,
    Organization,
    Review,
    ReviewStatus,
    Role,
    RoleAssignment,
    Submission,
    SubmissionVersion,
    User,
    UserStatus,
)


client = TestClient(app, base_url="http://localhost")
operator_headers = {"X-Fixture-Role": "OPERATOR"}
learner_headers = {"X-Fixture-Role": "LEARNER"}
reviewer_headers = {"X-Fixture-Role": "REVIEWER"}


def assert_ok(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def create_scoped_user(organization_id: uuid.UUID, role: Role, label: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(
            User(
                id=user_id,
                organization_id=organization_id,
                display_name=label,
                status=UserStatus.ACTIVE,
            )
        )
        session.flush()
        session.add(
            RoleAssignment(
                id=uuid.uuid4(),
                organization_id=organization_id,
                user_id=user_id,
                role=role,
            )
        )
    return user_id


def create_enrollment(
    *,
    assignment_status: AssignmentStatus = AssignmentStatus.AVAILABLE,
    review_status: ReviewStatus | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID | None]:
    learner_id = create_scoped_user(ORGANIZATION_ID, Role.LEARNER, "WP-06 合成运营新人")
    enrollment_id = uuid.uuid4()
    assignment_id = uuid.uuid4()
    review_id: uuid.UUID | None = None
    with SessionLocal.begin() as session:
        session.add(
            Enrollment(
                id=enrollment_id,
                organization_id=ORGANIZATION_ID,
                learner_id=learner_id,
                reviewer_id=REVIEWER_ID,
                status=EnrollmentStatus.ACTIVE,
                revision=1,
            )
        )
        session.flush()
        session.add(
            Assignment(
                id=assignment_id,
                organization_id=ORGANIZATION_ID,
                enrollment_id=enrollment_id,
                task_definition_id=TASK_DEFINITION_ID,
                task_version_id=TASK_VERSION_ID,
                position=1,
                status=assignment_status,
                revision=1,
            )
        )
        if review_status is not None:
            submission = Submission(
                id=uuid.uuid4(),
                organization_id=ORGANIZATION_ID,
                assignment_id=assignment_id,
                current_version_no=1,
            )
            session.add(submission)
            session.flush()
            version = SubmissionVersion(
                id=uuid.uuid4(),
                submission_id=submission.id,
                version_no=1,
                body="用于 WP-06 受控 Reviewer 重分配测试的合成提交正文，内容不含真实业务或个人信息。",
                created_by=learner_id,
            )
            session.add(version)
            session.flush()
            review_id = uuid.uuid4()
            session.add(
                Review(
                    id=review_id,
                    organization_id=ORGANIZATION_ID,
                    assignment_id=assignment_id,
                    submission_id=submission.id,
                    submission_version_id=version.id,
                    reviewer_id=REVIEWER_ID,
                    status=review_status,
                    revision=2 if review_status == ReviewStatus.IN_REVIEW else 1,
                    started_at=datetime.now(UTC) if review_status == ReviewStatus.IN_REVIEW else None,
                )
            )
    return enrollment_id, assignment_id, review_id


def command_headers(key: str) -> dict[str, str]:
    return {**operator_headers, "Idempotency-Key": key}


def test_ops_enrollment_commands_are_scoped_reasoned_idempotent_and_audited():
    enrollment_id, assignment_id, _ = create_enrollment()
    replacement_reviewer = create_scoped_user(ORGANIZATION_ID, Role.REVIEWER, "WP-06 替补主管")
    payload = {
        "expected_revision": 1,
        "reviewer_id": str(replacement_reviewer),
        "reason": "原主管在本地演练窗口不可用，需要受控重新分配。",
    }
    key = f"assign-reviewer-{uuid.uuid4()}"
    first = assert_ok(
        client.put(
            f"/api/v1/ops/enrollments/{enrollment_id}/reviewer",
            headers=command_headers(key),
            json=payload,
        )
    )
    replay = assert_ok(
        client.put(
            f"/api/v1/ops/enrollments/{enrollment_id}/reviewer",
            headers=command_headers(key),
            json=payload,
        )
    )
    assert first["revision"] == 2
    assert replay["idempotency_replay"] is True
    assert replay["reviewer_id"] == str(replacement_reviewer)

    listed = assert_ok(client.get("/api/v1/ops/enrollments", headers=operator_headers))
    item = next(row for row in listed["items"] if row["id"] == str(enrollment_id))
    assert item["allowed_commands"] == ["assign_reviewer", "cancel_enrollment"]
    assert item["assignment_statuses"] == ["AVAILABLE"]

    audit = assert_ok(
        client.get(
            "/api/v1/ops/audit",
            headers=operator_headers,
            params={"action": "enrollment.reviewer_assigned", "resource_id": str(enrollment_id)},
        )
    )
    assert len(audit["items"]) == 1
    assert "reason" in audit["items"][0]["redacted_fields"]
    assert "previous_reviewer_id" in audit["items"][0]["redacted_fields"]
    assert "reason" not in audit["items"][0]["safe_details"]

    cancel_key = f"cancel-enrollment-{uuid.uuid4()}"
    cancelled = assert_ok(
        client.post(
            f"/api/v1/ops/enrollments/{enrollment_id}/cancel",
            headers=command_headers(cancel_key),
            json={
                "expected_revision": 2,
                "reason": "本地取消演练验证有原因命令且不覆盖历史。",
            },
        )
    )
    assert cancelled["status"] == "CANCELLED"
    with SessionLocal() as session:
        assert session.get(Enrollment, enrollment_id).status == EnrollmentStatus.CANCELLED
        assert session.get(Assignment, assignment_id).status == AssignmentStatus.CANCELLED
        audit_row = session.scalar(
            select(AuditEntry).where(
                AuditEntry.action == "enrollment.cancelled",
                AuditEntry.resource_id == enrollment_id,
            )
        )
        assert audit_row is not None and audit_row.details["reason"]


def test_reviewer_reassignment_blocks_any_existing_review_history():
    enrollment_id, _, _ = create_enrollment(
        assignment_status=AssignmentStatus.SUBMITTED,
        review_status=ReviewStatus.ASSIGNED,
    )
    replacement_reviewer = create_scoped_user(ORGANIZATION_ID, Role.REVIEWER, "WP-06 新评审主管")
    assigned_blocked = client.put(
        f"/api/v1/ops/enrollments/{enrollment_id}/reviewer",
        headers=command_headers(f"replace-review-{uuid.uuid4()}"),
        json={
            "expected_revision": 1,
            "reviewer_id": str(replacement_reviewer),
            "reason": "已有评审记录时必须阻断，不能静默更换主管。",
        },
    )
    assert assigned_blocked.status_code == 409
    assert assigned_blocked.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    started_enrollment_id, _, _ = create_enrollment(
        assignment_status=AssignmentStatus.IN_REVIEW,
        review_status=ReviewStatus.IN_REVIEW,
    )
    blocked = client.put(
        f"/api/v1/ops/enrollments/{started_enrollment_id}/reviewer",
        headers=command_headers(f"blocked-review-{uuid.uuid4()}"),
        json={
            "expected_revision": 1,
            "reviewer_id": str(replacement_reviewer),
            "reason": "进行中评审同样必须被受控阻断而不是静默移动。",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_ops_permissions_cross_org_audit_filters_and_runtime_status_fail_closed():
    for headers in ({}, learner_headers, reviewer_headers):
        assert client.get("/api/v1/ops/enrollments", headers=headers).status_code in {401, 403}
        assert client.get("/api/v1/ops/audit", headers=headers).status_code in {401, 403}
        assert client.get("/api/v1/ops/runtime-status", headers=headers).status_code in {401, 403}
    assert client.get(
        "/api/v1/ops/audit", headers=operator_headers, params={"action": "bad filter!"}
    ).status_code == 400
    assert client.get(
        "/api/v1/ops/audit",
        headers=operator_headers,
        params={
            "occurred_after": "2026-01-01T00:00:00Z",
            "occurred_before": "2026-03-01T00:00:00Z",
        },
    ).status_code == 400

    other_org_id = uuid.uuid4()
    other_learner_id = uuid.uuid4()
    other_reviewer_id = uuid.uuid4()
    other_enrollment_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=other_org_id, name="WP-06 isolated organization"))
        session.add_all(
            [
                User(
                    id=other_learner_id,
                    organization_id=other_org_id,
                    display_name="isolated learner",
                    status=UserStatus.ACTIVE,
                ),
                User(
                    id=other_reviewer_id,
                    organization_id=other_org_id,
                    display_name="isolated reviewer",
                    status=UserStatus.ACTIVE,
                ),
            ]
        )
        session.flush()
        session.add(
            Enrollment(
                id=other_enrollment_id,
                organization_id=other_org_id,
                learner_id=other_learner_id,
                reviewer_id=other_reviewer_id,
                status=EnrollmentStatus.ACTIVE,
                revision=1,
            )
        )
    hidden = client.post(
        f"/api/v1/ops/enrollments/{other_enrollment_id}/cancel",
        headers=command_headers(f"cross-org-{uuid.uuid4()}"),
        json={"expected_revision": 1, "reason": "跨组织对象必须按存在性隐藏并拒绝操作。"},
    )
    assert hidden.status_code == 404
    runtime = assert_ok(client.get("/api/v1/ops/runtime-status", headers=operator_headers))
    assert runtime["migration_revision"] == "0010_wp06_governance"
    assert runtime["config_schema_version"] == 1
    assert runtime["external_observability_confirmed"] is False
    assert runtime["observability_mode"] == "LOCAL_STRUCTURED_STDOUT"
    assert set(runtime["metrics"]) == {
        "outbox_backlog",
        "notification_dead",
        "permission_denials_24h",
    }


def resign_package(package_dir, *, source_key: str, display_name: str) -> None:
    settings = get_settings()
    data_path = package_dir / offline_import.DATA_PATH
    record = json.loads(data_path.read_text())
    record["source_key"] = source_key
    record["learner_display_name"] = display_name
    data_bytes = offline_import.canonical_json(record) + b"\n"
    data_path.write_bytes(data_bytes)
    checksum_bytes = (
        f"{hashlib.sha256(data_bytes).hexdigest()}  {offline_import.DATA_PATH}\n".encode()
    )
    (package_dir / "checksums.sha256").write_bytes(checksum_bytes)
    manifest_bytes = (package_dir / "manifest.json").read_bytes()
    signature = hmac.new(
        settings.import_signing_key.encode(),
        manifest_bytes + b"\n" + checksum_bytes,
        hashlib.sha256,
    ).hexdigest()
    (package_dir / "signature").write_text(signature + "\n")


def test_signed_offline_import_is_idempotent_replay_safe_and_quarantines_conflicts(tmp_path):
    package = tmp_path / "package-a"
    offline_import.create_fixture_package(package)
    before = None
    before_batches = None
    with SessionLocal() as session:
        before = session.scalar(select(func.count(Enrollment.id)))
        before_batches = session.scalar(select(func.count(ImportBatch.id)))
    dry_run = offline_import.dry_run_package(package)
    assert dry_run["status"] == "DRY_RUN_CLEAN"
    assert dry_run["mode"] == "DRY_RUN"
    assert dry_run["would_import_count"] == 1
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Enrollment.id))) == before
        assert session.scalar(select(func.count(ImportBatch.id))) == before_batches
    first = offline_import.apply_package(package)
    replay = offline_import.apply_package(package)
    assert first["status"] == "APPLIED"
    assert first["mode"] == "APPLY"
    assert first["imported_count"] == 1
    assert replay["package_replay"] is True
    assert replay["replayed_count"] == 1
    assert first["contains_record_identifiers"] is False
    assert first["source_writeback_executed"] is False
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Enrollment.id))) == before + 1
        batch = session.scalar(
            select(ImportBatch).where(ImportBatch.package_checksum == first["package_checksum"])
        )
        assert batch is not None
        record = session.scalar(select(ImportRecord).where(ImportRecord.batch_id == batch.id))
        assert record.status == "IMPORTED" and record.target_id is not None
        original_key = record.source_key

    conflicting = tmp_path / "package-b"
    offline_import.create_fixture_package(conflicting)
    resign_package(conflicting, source_key=original_key, display_name="冲突内容必须进入隔离")
    conflict_report = offline_import.apply_package(conflicting)
    assert conflict_report["status"] == "APPLIED_WITH_QUARANTINE"
    assert conflict_report["imported_count"] == 0
    assert conflict_report["quarantined_count"] == 1
    assert conflict_report["quarantine_reason_counts"] == {"SOURCE_KEY_CONFLICT": 1}
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Enrollment.id))) == before + 1

    try:
        with SessionLocal.begin() as session:
            session.execute(update(ImportBatch).values(status="APPLIED"))
    except DBAPIError as exc:
        assert "immutable" in str(exc).lower()
    else:
        raise AssertionError("Import history update unexpectedly succeeded")


def test_signed_offline_import_serializes_concurrent_package_replay(tmp_path):
    package = tmp_path / "package-concurrent"
    offline_import.create_fixture_package(package)
    with SessionLocal() as session:
        enrollments_before = session.scalar(select(func.count(Enrollment.id)))
    with ThreadPoolExecutor(max_workers=2) as executor:
        reports = list(executor.map(lambda _: offline_import.apply_package(package), range(2)))
    assert sorted(report["package_replay"] for report in reports) == [False, True]
    assert sum(report["imported_count"] for report in reports) == 1
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Enrollment.id))) == enrollments_before + 1


def test_offline_import_rejects_tampering_and_nonlocal_runtime(tmp_path, monkeypatch):
    package = tmp_path / "tampered"
    offline_import.create_fixture_package(package)
    with (package / offline_import.DATA_PATH).open("ab") as stream:
        stream.write(b"tampered\n")
    with pytest.raises(offline_import.PackageError, match="checksum"):
        offline_import.apply_package(package)

    production = Settings(
        app_env="production",
        allow_fixture_identity=False,
        session_secret="production-session-secret-example-123456",
        invite_secret="production-invite-secret-example-1234567",
        import_signing_key="production-import-signing-key-example-123456",
    )
    monkeypatch.setattr(offline_import, "get_settings", lambda: production)
    with pytest.raises(offline_import.PackageError, match="disabled outside local/test"):
        offline_import.verify_package(package)
