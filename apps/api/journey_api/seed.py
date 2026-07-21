from sqlalchemy import select

from journey_api.db import SessionLocal
from journey_api.fixtures import (
    ASSIGNMENT_ID,
    ENROLLMENT_ID,
    LEARNER_ID,
    LEARNER_ROLE_ID,
    ORGANIZATION_ID,
    OPERATOR_ID,
    OPERATOR_ROLE_ID,
    REVIEWER_ID,
    REVIEWER_ROLE_ID,
    TASK_DEFINITION_ID,
    TASK_VERSION_ID,
    TASK_VERSION_V2_ID,
)
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Enrollment,
    EnrollmentStatus,
    Organization,
    Role,
    RoleAssignment,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
    User,
    UserStatus,
)

RUBRIC = {
    "version": 1,
    "dimensions": [
        {
            "dimension_key": "problem_clarity",
            "title": "问题清晰度",
            "purpose": "确认问题、受影响对象和边界具体清楚。",
            "evidence_expected": "问题说明中的对象、场景和边界。",
            "levels": {"MEETS": "问题具体且边界清楚", "NEEDS_WORK": "问题仍宽泛或对象不清"},
            "required": True,
            "feedback_prompt": "指出需要缩小或补充的对象与边界。",
            "blocking_rule": "REQUIRE_FEEDBACK",
        },
        {
            "dimension_key": "evidence_quality",
            "title": "依据质量",
            "purpose": "确认事实可核对且与假设分开。",
            "evidence_expected": "至少两条事实或观察。",
            "levels": {"MEETS": "两条以上依据可核对", "NEEDS_WORK": "依据不足或事实假设混淆"},
            "required": True,
            "feedback_prompt": "指出需要补充或澄清的依据。",
            "blocking_rule": "REQUIRE_FEEDBACK",
        },
        {
            "dimension_key": "action_feasibility",
            "title": "行动可执行性",
            "purpose": "确认建议短、具体且责任明确。",
            "evidence_expected": "三步以内的行动、责任人和第一步。",
            "levels": {"MEETS": "第一步与责任人明确", "NEEDS_WORK": "行动不可执行或责任不清"},
            "required": True,
            "feedback_prompt": "指出不可执行或责任不清之处。",
            "blocking_rule": "REQUIRE_FEEDBACK",
        },
        {
            "dimension_key": "validation_design",
            "title": "验证设计",
            "purpose": "确认两周内能够验证并安全停止或调整。",
            "evidence_expected": "验证指标和停止或调整条件。",
            "levels": {"MEETS": "指标与护栏可观察", "NEEDS_WORK": "无法验证或缺少护栏"},
            "required": True,
            "feedback_prompt": "指出无法验证或缺少护栏之处。",
            "blocking_rule": "REQUIRE_FEEDBACK",
        },
    ],
}

INSTRUCTIONS = [
    "用 100–200 字说明一个真实、具体的问题及受影响对象。",
    "提供至少两条可核对的事实或观察，区分事实与假设。",
    "给出三步以内的行动建议，写明责任人和第一步。",
    "给出一个可在两周内观察的验证指标与停止或调整条件。",
]
COMPLETION_CRITERIA = [
    "问题、对象和边界清楚",
    "至少两条依据可核对",
    "行动不超过三步且第一步明确",
    "包含两周内可观察的指标和护栏",
]
REQUIRED_DELIVERABLES = [
    "100–200 字的问题说明",
    "至少两条可核对的事实或观察",
    "三步以内的行动建议（含责任人和第一步）",
    "两周内可观察的验证指标与停止或调整条件",
]


def seed() -> None:
    with SessionLocal.begin() as session:
        if session.get(Organization, ORGANIZATION_ID) is None:
            session.add(Organization(id=ORGANIZATION_ID, name="Muchen Journey Fixture"))
            session.flush()
        users = (
            (LEARNER_ID, "试点新人"),
            (REVIEWER_ID, "试点主管"),
            (OPERATOR_ID, "试点运营"),
        )
        for user_id, display_name in users:
            if session.get(User, user_id) is None:
                session.add(
                    User(
                        id=user_id,
                        organization_id=ORGANIZATION_ID,
                        display_name=display_name,
                        status=UserStatus.ACTIVE,
                    )
                )
        session.flush()
        roles = (
            (LEARNER_ROLE_ID, LEARNER_ID, Role.LEARNER),
            (REVIEWER_ROLE_ID, REVIEWER_ID, Role.REVIEWER),
            (OPERATOR_ROLE_ID, OPERATOR_ID, Role.OPERATOR),
        )
        for role_id, user_id, role in roles:
            if session.get(RoleAssignment, role_id) is None:
                session.add(
                    RoleAssignment(
                        id=role_id,
                        organization_id=ORGANIZATION_ID,
                        user_id=user_id,
                        role=role,
                    )
                )
        session.flush()

        task_definition = session.scalar(
            select(TaskDefinition).where(
                TaskDefinition.organization_id == ORGANIZATION_ID,
                TaskDefinition.stable_key == "TSK-001",
            )
        )
        if task_definition is None:
            task_definition = TaskDefinition(
                id=TASK_DEFINITION_ID,
                organization_id=ORGANIZATION_ID,
                stable_key="TSK-001",
                status=TaskDefinitionStatus.PUBLISHED,
                revision=1,
                created_by=OPERATOR_ID,
            )
            session.add(task_definition)
            session.flush()
        if session.get(TaskVersion, TASK_VERSION_ID) is None:
            session.add(
                TaskVersion(
                    id=TASK_VERSION_ID,
                    organization_id=ORGANIZATION_ID,
                    task_definition_id=task_definition.id,
                    version=1,
                    title="问题洞察与行动建议",
                    purpose="把一个真实问题转化为有依据、可执行、可验证的行动方案。",
                    learner_outcome="能够把真实问题转化为有依据、可执行、可验证的行动方案。",
                    instructions=INSTRUCTIONS,
                    completion_criteria=COMPLETION_CRITERIA,
                    required_deliverables=REQUIRED_DELIVERABLES,
                    content_source_notes=["批准文档 03、04、05 与 15 中的 TSK-001 V1 合同"],
                    change_summary="建立首个可发布的 TSK-001 V1 任务内容合同。",
                    reviewer_calibration_note="本地 fixture Rubric；真人 Reviewer 校准仍为 NOT_RUN 门禁。",
                    allowed_attachment_types=[],
                    max_attachment_size_bytes=0,
                    reference_materials=[],
                    estimated_duration_minutes=60,
                    rubric=RUBRIC,
                    rubric_version=1,
                    reviewer_role="REVIEWER",
                    feedback_sla_business_days=2,
                    sensitivity="INTERNAL",
                    audience="LEARNER",
                    published_by=OPERATOR_ID,
                    reviewed_by=REVIEWER_ID,
                )
            )
        if session.get(TaskVersion, TASK_VERSION_V2_ID) is None:
            session.add(
                TaskVersion(
                    id=TASK_VERSION_V2_ID,
                    organization_id=ORGANIZATION_ID,
                    task_definition_id=task_definition.id,
                    version=2,
                    title="问题洞察与行动建议",
                    purpose="把一个真实问题转化为有依据、可执行、可验证的行动方案。",
                    learner_outcome="能够把真实问题转化为有依据、可执行、可验证的行动方案。",
                    instructions=INSTRUCTIONS,
                    completion_criteria=COMPLETION_CRITERIA,
                    required_deliverables=REQUIRED_DELIVERABLES,
                    content_source_notes=["批准文档 03、04、05、07、08 与 15 的 WP-03 附件合同"],
                    change_summary="增加受控文本、PDF、PNG、JPEG 附件与 5 MiB 上限。",
                    reviewer_calibration_note="本地附件合同样本；真人 Reviewer 校准仍为 NOT_RUN 门禁。",
                    allowed_attachment_types=[
                        "text/plain",
                        "application/pdf",
                        "image/png",
                        "image/jpeg",
                    ],
                    max_attachment_size_bytes=5 * 1024 * 1024,
                    reference_materials=[],
                    estimated_duration_minutes=60,
                    rubric=RUBRIC,
                    rubric_version=1,
                    reviewer_role="REVIEWER",
                    feedback_sla_business_days=2,
                    sensitivity="INTERNAL",
                    audience="LEARNER",
                    published_by=OPERATOR_ID,
                    reviewed_by=REVIEWER_ID,
                )
            )
            if task_definition.revision < 2:
                task_definition.revision = 2
        if session.get(Enrollment, ENROLLMENT_ID) is None:
            session.add(
                Enrollment(
                    id=ENROLLMENT_ID,
                    organization_id=ORGANIZATION_ID,
                    learner_id=LEARNER_ID,
                    reviewer_id=REVIEWER_ID,
                    status=EnrollmentStatus.ACTIVE,
                    revision=1,
                )
            )
        session.flush()
        if session.get(Assignment, ASSIGNMENT_ID) is None:
            session.add(
                Assignment(
                    id=ASSIGNMENT_ID,
                    organization_id=ORGANIZATION_ID,
                    enrollment_id=ENROLLMENT_ID,
                    task_definition_id=task_definition.id,
                    task_version_id=TASK_VERSION_ID,
                    position=1,
                    status=AssignmentStatus.AVAILABLE,
                    revision=1,
                )
            )


if __name__ == "__main__":
    seed()
