import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from journey_api.db import SessionLocal
from journey_api.fixtures import (
    ENROLLMENT_ID,
    LEARNER_ID,
    ORGANIZATION_ID,
    REVIEWER_ID,
)
from journey_api.main import app
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    AuditEntry,
    Enrollment,
    EnrollmentStatus,
    Organization,
    OutboxEvent,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
    User,
    UserStatus,
)


client = TestClient(app, base_url="http://localhost")
operator_headers = {"X-Fixture-Role": "OPERATOR"}
learner_headers = {"X-Fixture-Role": "LEARNER"}
reviewer_headers = {"X-Fixture-Role": "REVIEWER"}


def assert_ok(response):
    assert response.status_code < 400, response.text
    assert response.headers["X-Request-ID"].startswith("req_")
    return response.json()["data"]


def publish_payload(*, expected_revision: int, title: str = "试点任务版本") -> dict[str, object]:
    dimensions = [
        ("problem_clarity", "问题清晰度", "确认问题对象、场景和边界具体清楚。"),
        ("evidence_quality", "依据质量", "确认事实可核对并且和假设明确分开。"),
        ("action_feasibility", "行动可行性", "确认行动短而具体并且责任清楚。"),
        ("validation_design", "验证设计", "确认两周内能够验证并安全停止调整。"),
    ]
    return {
        "expected_revision": expected_revision,
        "title": title,
        "purpose": "帮助新人把一个真实问题转化为可执行且可验证的行动方案。",
        "learner_outcome": "能够清楚说明问题、引用可核对依据，并提出带验证护栏的行动。",
        "instructions": [
            "说明问题、受影响对象和清楚边界。",
            "列出至少两条可核对的事实或观察。",
            "给出三步以内的行动以及两周验证方式。",
        ],
        "completion_criteria": [
            "问题与边界清楚",
            "至少两条依据可核对",
            "行动责任和验证护栏明确",
        ],
        "required_deliverables": [
            "问题说明",
            "事实或观察",
            "行动建议和验证指标",
        ],
        "content_source_notes": ["自动化合同样本，来源为批准文档 15 的 TSK-001 结构。"],
        "change_summary": "自动化验证用的首个不可变任务版本。",
        "reviewer_calibration_note": "仅为自动化合同样本；真人 Reviewer 校准保持 NOT_RUN。",
        "allowed_attachment_types": [],
        "max_attachment_size_bytes": 0,
        "reference_materials": ["探索营任务说明"],
        "estimated_duration_minutes": 45,
        "rubric": {
            "version": 1,
            "dimensions": [
                {
                    "dimension_key": key,
                    "title": title,
                    "purpose": purpose,
                    "evidence_expected": "提交内容中可直接定位的对应依据。",
                    "levels": {
                        "MEETS": "达到本维度的明确要求",
                        "NEEDS_WORK": "本维度仍需具体补充",
                    },
                    "required": True,
                    "feedback_prompt": "指出具体缺口并说明下一步如何补充。",
                    "blocking_rule": "REQUIRE_FEEDBACK",
                }
                for key, title, purpose in dimensions
            ],
        },
        "reviewer_role": "REVIEWER",
        "feedback_sla_business_days": 2,
        "sensitivity": "INTERNAL",
        "audience": "LEARNER",
        "reviewed_by": str(REVIEWER_ID),
    }


def create_definition(stable_key: str) -> dict[str, object]:
    return assert_ok(
        client.post(
            "/api/v1/ops/task-definitions",
            headers={**operator_headers, "Idempotency-Key": f"create-{uuid.uuid4()}"},
            json={"stable_key": stable_key},
        )
    )


def publish(definition_id: str, payload: dict[str, object], *, key: str | None = None):
    return client.post(
        f"/api/v1/ops/task-definitions/{definition_id}/publish",
        headers={**operator_headers, "Idempotency-Key": key or f"publish-{uuid.uuid4()}"},
        json=payload,
    )


def test_task_definition_and_publish_permissions_are_fail_closed():
    for headers in (learner_headers, reviewer_headers):
        assert (
            client.post(
                "/api/v1/ops/task-definitions",
                headers={**headers, "Idempotency-Key": f"forbidden-{uuid.uuid4()}"},
                json={"stable_key": f"TSK-FORBIDDEN-{uuid.uuid4().hex[:8].upper()}"},
            ).status_code
            == 403
        )
        assert client.get("/api/v1/ops/task-definitions", headers=headers).status_code == 403

    not_found = publish(str(uuid.uuid4()), publish_payload(expected_revision=1))
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "NOT_FOUND"

    other_org_id = uuid.uuid4()
    other_owner_id = uuid.uuid4()
    other_definition_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=other_org_id, name="Other organization"))
        session.add(
            User(
                id=other_owner_id,
                organization_id=other_org_id,
                display_name="Other content owner",
                status=UserStatus.ACTIVE,
            )
        )
        session.flush()
        session.add(
            TaskDefinition(
                id=other_definition_id,
                organization_id=other_org_id,
                stable_key=f"TSK-OTHER-{uuid.uuid4().hex[:8].upper()}",
                status=TaskDefinitionStatus.DRAFT,
                revision=1,
                created_by=other_owner_id,
            )
        )
    scoped = publish(str(other_definition_id), publish_payload(expected_revision=1))
    assert scoped.status_code == 404


def test_publish_validates_scope_contract_revision_and_idempotency():
    definition = create_definition(f"TSK-CONTRACT-{uuid.uuid4().hex[:8].upper()}")
    assert definition["status"] == "DRAFT"
    assert definition["revision"] == 1
    assert definition["content_owner_id"]

    invalid_reviewer = publish_payload(expected_revision=1)
    invalid_reviewer["reviewed_by"] = str(LEARNER_ID)
    rejected = publish(str(definition["id"]), invalid_reviewer)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "VALIDATION_FAILED"

    attachment_payload = publish_payload(expected_revision=1)
    attachment_payload["allowed_attachment_types"] = ["application/pdf"]
    assert publish(str(definition["id"]), attachment_payload).status_code == 422

    extra_payload = {**publish_payload(expected_revision=1), "unapproved_field": "no"}
    assert publish(str(definition["id"]), extra_payload).status_code == 422

    payload = publish_payload(expected_revision=1)
    key = f"publish-idempotent-{uuid.uuid4()}"
    first = assert_ok(publish(str(definition["id"]), payload, key=key))
    replay = assert_ok(publish(str(definition["id"]), payload, key=key))
    assert first["id"] == replay["id"]
    assert first["version"] == 1
    assert replay["idempotency_replay"] is True
    assert first["rubric_version"] == 1
    assert first["allowed_attachment_types"] == []
    assert first["max_attachment_size_bytes"] == 0
    assert first["content_source_notes"]
    assert "真人 Reviewer" in first["reviewer_calibration_note"]
    assert first["change_summary"]

    conflict = publish(str(definition["id"]), publish_payload(expected_revision=1))
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "VERSION_CONFLICT"

    listed = assert_ok(client.get("/api/v1/ops/task-definitions", headers=operator_headers))
    matching = next(item for item in listed["items"] if item["id"] == definition["id"])
    assert matching["status"] == "PUBLISHED"
    assert matching["revision"] == 2
    assert [item["version"] for item in matching["versions"]] == [1]

    with SessionLocal() as session:
        stored_definition = session.get(TaskDefinition, uuid.UUID(str(definition["id"])))
        assert stored_definition is not None
        assert stored_definition.organization_id == ORGANIZATION_ID
        assert stored_definition.status == TaskDefinitionStatus.PUBLISHED
        assert session.scalar(
            select(AuditEntry.id).where(
                AuditEntry.action == "task_version.published",
                AuditEntry.resource_id == uuid.UUID(str(first["id"])),
            )
        )
        assert session.scalar(
            select(OutboxEvent.id).where(
                OutboxEvent.event_type == "task_version.published.v1",
                OutboxEvent.aggregate_id == uuid.UUID(str(definition["id"])),
            )
        )


def test_published_task_version_is_immutable_in_database():
    definition = create_definition(f"TSK-IMMUTABLE-{uuid.uuid4().hex[:8].upper()}")
    version = assert_ok(publish(str(definition["id"]), publish_payload(expected_revision=1)))
    version_id = uuid.UUID(str(version["id"]))

    try:
        with SessionLocal.begin() as session:
            session.execute(
                update(TaskVersion).where(TaskVersion.id == version_id).values(title="被篡改")
            )
    except DBAPIError as error:
        assert "immutable" in str(error).lower()
    else:
        raise AssertionError("published TaskVersion update unexpectedly succeeded")

    try:
        with SessionLocal.begin() as session:
            session.execute(delete(TaskVersion).where(TaskVersion.id == version_id))
    except DBAPIError as error:
        assert "immutable" in str(error).lower()
    else:
        raise AssertionError("published TaskVersion delete unexpectedly succeeded")

    with SessionLocal() as session:
        stored = session.get(TaskVersion, version_id)
        assert stored is not None
        assert stored.title == version["title"]


def test_assignment_stays_on_v1_when_v2_is_published_and_drives_current_action():
    definition = create_definition(f"TSK-FIXED-{uuid.uuid4().hex[:8].upper()}")
    version_one = assert_ok(
        publish(str(definition["id"]), publish_payload(expected_revision=1, title="固定版本一"))
    )
    assignment_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        enrollment = session.get(Enrollment, ENROLLMENT_ID)
        assert enrollment is not None
        enrollment.status = EnrollmentStatus.ACTIVE
        enrollment.revision += 1
        session.add(
            Assignment(
                id=assignment_id,
                organization_id=ORGANIZATION_ID,
                enrollment_id=ENROLLMENT_ID,
                task_definition_id=uuid.UUID(str(definition["id"])),
                task_version_id=uuid.UUID(str(version_one["id"])),
                position=2,
                status=AssignmentStatus.AVAILABLE,
                revision=1,
            )
        )

    version_two = assert_ok(
        publish(str(definition["id"]), publish_payload(expected_revision=2, title="新发布版本二"))
    )
    assert version_two["version"] == 2

    detail = assert_ok(
        client.get(f"/api/v1/me/assignments/{assignment_id}", headers=learner_headers)
    )
    assert detail["task_version"] == 1
    assert detail["task_title"] == "固定版本一"
    assert detail["allowed_commands"] == ["start"]
    assert detail["learner_outcome"]
    assert detail["required_deliverables"]
    assert {item["dimension_key"] for item in detail["rubric"]["dimensions"]} == {
        "problem_clarity",
        "evidence_quality",
        "action_feasibility",
        "validation_design",
    }

    current = assert_ok(client.get("/api/v1/me/current-action", headers=learner_headers))
    assert current["resource_id"] == str(assignment_id)
    assert current["action_type"] == "START_OR_CONTINUE_TASK"
    assert current["stage"] == "当前任务"
    assert current["responsible_party"] == "试点主管"
    assert current["feedback_expectation"] == "2 个工作日内"

    with SessionLocal() as session:
        assignment = session.get(Assignment, assignment_id)
        assert assignment is not None
        assert assignment.task_version_id == uuid.UUID(str(version_one["id"]))
        assert assignment.task_version_id != uuid.UUID(str(version_two["id"]))


def test_assignment_detail_does_not_leak_another_learners_task():
    definition = create_definition(f"TSK-IDOR-{uuid.uuid4().hex[:8].upper()}")
    version = assert_ok(publish(str(definition["id"]), publish_payload(expected_revision=1)))
    other_learner_id = uuid.uuid4()
    other_enrollment_id = uuid.uuid4()
    other_assignment_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(
            User(
                id=other_learner_id,
                organization_id=ORGANIZATION_ID,
                display_name="另一位新人",
                status=UserStatus.ACTIVE,
            )
        )
        session.flush()
        session.add(
            Enrollment(
                id=other_enrollment_id,
                organization_id=ORGANIZATION_ID,
                learner_id=other_learner_id,
                reviewer_id=REVIEWER_ID,
                status=EnrollmentStatus.ACTIVE,
                revision=1,
            )
        )
        session.flush()
        session.add(
            Assignment(
                id=other_assignment_id,
                organization_id=ORGANIZATION_ID,
                enrollment_id=other_enrollment_id,
                task_definition_id=uuid.UUID(str(definition["id"])),
                task_version_id=uuid.UUID(str(version["id"])),
                position=1,
                status=AssignmentStatus.AVAILABLE,
                revision=1,
            )
        )
    response = client.get(
        f"/api/v1/me/assignments/{other_assignment_id}", headers=learner_headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
