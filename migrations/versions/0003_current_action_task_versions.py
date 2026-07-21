"""Add WP-02 task definitions, immutable task versions, and assignment ordering.

Revision ID: 0003_current_action_tasks
Revises: 0002_invites_identity_sessions
"""

import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0003_current_action_tasks"
down_revision = "0002_invites_identity_sessions"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)

TSK_001_OUTCOME = "能够把真实问题转化为有依据、可执行、可验证的行动方案。"
TSK_001_DELIVERABLES = [
    "100–200 字的问题说明",
    "至少两条可核对的事实或观察",
    "三步以内的行动建议（含责任人和第一步）",
    "两周内可观察的验证指标与停止或调整条件",
]
RUBRIC_V1 = {
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


def _backfill_task_contract() -> None:
    bind = op.get_bind()
    definitions: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
    versions = (
        bind.execute(sa.text("SELECT id, stable_key FROM task_versions ORDER BY id"))
        .mappings()
        .all()
    )
    for version in versions:
        task_version_id = version["id"]
        stable_key = version["stable_key"]
        organization_id = bind.execute(
            sa.text(
                """
                SELECT organization_id
                FROM assignments
                WHERE task_version_id = :task_version_id
                UNION ALL
                SELECT organization_id
                FROM invites
                WHERE task_version_id = :task_version_id
                LIMIT 1
                """
            ),
            {"task_version_id": task_version_id},
        ).scalar()
        if organization_id is None:
            organization_id = bind.execute(
                sa.text("SELECT id FROM organizations ORDER BY id LIMIT 1")
            ).scalar()
        if organization_id is None:
            raise RuntimeError("TaskVersion cannot be migrated without an organization")

        owner_id = bind.execute(
            sa.text(
                """
                SELECT ra.user_id
                FROM role_assignments AS ra
                JOIN users AS u ON u.id = ra.user_id
                WHERE ra.organization_id = :organization_id
                  AND ra.role = 'OPERATOR'
                  AND u.status = 'ACTIVE'
                ORDER BY ra.user_id
                LIMIT 1
                """
            ),
            {"organization_id": organization_id},
        ).scalar()
        if owner_id is None:
            owner_id = bind.execute(
                sa.text(
                    "SELECT id FROM users WHERE organization_id = :organization_id ORDER BY id LIMIT 1"
                ),
                {"organization_id": organization_id},
            ).scalar()
        reviewer_id = bind.execute(
            sa.text(
                """
                SELECT ra.user_id
                FROM role_assignments AS ra
                JOIN users AS u ON u.id = ra.user_id
                WHERE ra.organization_id = :organization_id
                  AND ra.role = 'REVIEWER'
                  AND u.status = 'ACTIVE'
                ORDER BY ra.user_id
                LIMIT 1
                """
            ),
            {"organization_id": organization_id},
        ).scalar() or owner_id
        if owner_id is None or reviewer_id is None:
            raise RuntimeError("TaskVersion cannot be migrated without active content owners")

        key = (organization_id, stable_key)
        definition_id = definitions.get(key)
        if definition_id is None:
            definition_id = uuid.uuid4()
            definitions[key] = definition_id
            bind.execute(
                sa.text(
                    """
                    INSERT INTO task_definitions
                        (id, organization_id, stable_key, status, revision, created_by)
                    VALUES
                        (:id, :organization_id, :stable_key, 'PUBLISHED', 1, :created_by)
                    """
                ),
                {
                    "id": definition_id,
                    "organization_id": organization_id,
                    "stable_key": stable_key,
                    "created_by": owner_id,
                },
            )
        bind.execute(
            sa.text(
                """
                UPDATE task_versions
                SET organization_id = :organization_id,
                    task_definition_id = :task_definition_id,
                    learner_outcome = :learner_outcome,
                    required_deliverables = CAST(:required_deliverables AS JSON),
                    allowed_attachment_types = CAST('[]' AS JSON),
                    max_attachment_size_bytes = 0,
                    reference_materials = CAST('[]' AS JSON),
                    estimated_duration_minutes = 60,
                    rubric = CAST(:rubric AS JSON),
                    rubric_version = 1,
                    reviewer_role = 'REVIEWER',
                    feedback_sla_business_days = 2,
                    sensitivity = 'INTERNAL',
                    audience = 'LEARNER',
                    published_by = :published_by,
                    reviewed_by = :reviewed_by
                WHERE id = :task_version_id
                """
            ),
            {
                "organization_id": organization_id,
                "task_definition_id": definition_id,
                "learner_outcome": TSK_001_OUTCOME,
                "required_deliverables": json.dumps(TSK_001_DELIVERABLES, ensure_ascii=False),
                "rubric": json.dumps(RUBRIC_V1, ensure_ascii=False),
                "published_by": owner_id,
                "reviewed_by": reviewer_id,
                "task_version_id": task_version_id,
            },
        )


def upgrade() -> None:
    op.create_table(
        "task_definitions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("stable_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'WITHDRAWN')",
            name="ck_task_definitions_status",
        ),
        sa.UniqueConstraint(
            "organization_id", "stable_key", name="uq_task_definitions_organization_key"
        ),
    )
    op.create_index(
        "ix_task_definitions_organization_id", "task_definitions", ["organization_id"]
    )

    additions = (
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("task_definition_id", UUID, nullable=True),
        sa.Column("learner_outcome", sa.Text(), nullable=True),
        sa.Column("required_deliverables", sa.JSON(), nullable=True),
        sa.Column("allowed_attachment_types", sa.JSON(), nullable=True),
        sa.Column("max_attachment_size_bytes", sa.Integer(), nullable=True),
        sa.Column("reference_materials", sa.JSON(), nullable=True),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("rubric_version", sa.Integer(), nullable=True),
        sa.Column("reviewer_role", sa.String(40), nullable=True),
        sa.Column("feedback_sla_business_days", sa.Integer(), nullable=True),
        sa.Column("sensitivity", sa.String(40), nullable=True),
        sa.Column("audience", sa.String(40), nullable=True),
        sa.Column("published_by", UUID, nullable=True),
        sa.Column("reviewed_by", UUID, nullable=True),
    )
    for column in additions:
        op.add_column("task_versions", column)

    _backfill_task_contract()

    for column_name in (
        "organization_id",
        "task_definition_id",
        "learner_outcome",
        "required_deliverables",
        "allowed_attachment_types",
        "max_attachment_size_bytes",
        "reference_materials",
        "estimated_duration_minutes",
        "rubric_version",
        "reviewer_role",
        "feedback_sla_business_days",
        "sensitivity",
        "audience",
        "published_by",
        "reviewed_by",
    ):
        op.alter_column("task_versions", column_name, nullable=False)
    op.create_foreign_key(
        "fk_task_versions_organization",
        "task_versions",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_task_versions_definition",
        "task_versions",
        "task_definitions",
        ["task_definition_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_task_versions_published_by", "task_versions", "users", ["published_by"], ["id"]
    )
    op.create_foreign_key(
        "fk_task_versions_reviewed_by", "task_versions", "users", ["reviewed_by"], ["id"]
    )
    op.create_index(
        "ix_task_versions_organization_id", "task_versions", ["organization_id"]
    )
    op.create_index(
        "ix_task_versions_task_definition_id", "task_versions", ["task_definition_id"]
    )
    op.drop_constraint("uq_task_versions_key_version", "task_versions", type_="unique")
    op.drop_column("task_versions", "stable_key")
    op.create_unique_constraint(
        "uq_task_versions_definition_version",
        "task_versions",
        ["task_definition_id", "version"],
    )
    op.create_unique_constraint(
        "uq_task_versions_id_definition",
        "task_versions",
        ["id", "task_definition_id"],
    )
    op.create_check_constraint(
        "ck_task_versions_positive_version", "task_versions", "version >= 1"
    )
    op.create_check_constraint(
        "ck_task_versions_estimated_duration",
        "task_versions",
        "estimated_duration_minutes BETWEEN 1 AND 480",
    )
    op.create_check_constraint(
        "ck_task_versions_feedback_sla",
        "task_versions",
        "feedback_sla_business_days BETWEEN 1 AND 10",
    )
    op.create_check_constraint(
        "ck_task_versions_attachment_size",
        "task_versions",
        "max_attachment_size_bytes >= 0",
    )

    op.add_column("assignments", sa.Column("task_definition_id", UUID, nullable=True))
    op.add_column("assignments", sa.Column("position", sa.Integer(), nullable=True))
    op.add_column(
        "assignments",
        sa.Column("assigned_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        """
        UPDATE assignments AS a
        SET task_definition_id = tv.task_definition_id,
            position = ranked.position
        FROM task_versions AS tv,
             (
                 SELECT id,
                        row_number() OVER (PARTITION BY enrollment_id ORDER BY id)::integer AS position
                 FROM assignments
             ) AS ranked
        WHERE a.task_version_id = tv.id
          AND ranked.id = a.id
        """
    )
    op.alter_column("assignments", "task_definition_id", nullable=False)
    op.alter_column("assignments", "position", nullable=False)
    op.create_foreign_key(
        "fk_assignments_task_definition",
        "assignments",
        "task_definitions",
        ["task_definition_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_assignments_task_version_definition",
        "assignments",
        "task_versions",
        ["task_version_id", "task_definition_id"],
        ["id", "task_definition_id"],
    )
    op.create_unique_constraint(
        "uq_assignments_enrollment_task",
        "assignments",
        ["enrollment_id", "task_definition_id"],
    )
    op.create_unique_constraint(
        "uq_assignments_enrollment_position",
        "assignments",
        ["enrollment_id", "position"],
    )
    op.create_check_constraint(
        "ck_assignments_positive_position", "assignments", "position >= 1"
    )
    op.drop_constraint("ck_assignments_status", "assignments", type_="check")
    op.create_check_constraint(
        "ck_assignments_status",
        "assignments",
        "status IN ('AVAILABLE', 'IN_PROGRESS', 'SUBMITTED', 'IN_REVIEW', "
        "'NEEDS_REVISION', 'COMPLETED', 'CANCELLED')",
    )

    op.execute(
        """
        CREATE FUNCTION reject_task_version_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Published TaskVersion rows are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER task_versions_immutable
        BEFORE UPDATE OR DELETE ON task_versions
        FOR EACH ROW EXECUTE FUNCTION reject_task_version_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS task_versions_immutable ON task_versions")
    op.execute("DROP FUNCTION IF EXISTS reject_task_version_mutation()")

    op.drop_constraint("ck_assignments_status", "assignments", type_="check")
    op.create_check_constraint(
        "ck_assignments_status",
        "assignments",
        "status IN ('AVAILABLE', 'IN_PROGRESS', 'SUBMITTED', 'IN_REVIEW', "
        "'NEEDS_REVISION', 'COMPLETED')",
    )
    op.drop_constraint("ck_assignments_positive_position", "assignments", type_="check")
    op.drop_constraint("uq_assignments_enrollment_position", "assignments", type_="unique")
    op.drop_constraint("uq_assignments_enrollment_task", "assignments", type_="unique")
    op.drop_constraint(
        "fk_assignments_task_version_definition", "assignments", type_="foreignkey"
    )
    op.drop_constraint("fk_assignments_task_definition", "assignments", type_="foreignkey")
    op.drop_column("assignments", "assigned_at")
    op.drop_column("assignments", "position")
    op.drop_column("assignments", "task_definition_id")

    op.add_column("task_versions", sa.Column("stable_key", sa.String(80), nullable=True))
    op.execute(
        """
        UPDATE task_versions AS tv
        SET stable_key = td.stable_key
        FROM task_definitions AS td
        WHERE td.id = tv.task_definition_id
        """
    )
    op.alter_column("task_versions", "stable_key", nullable=False)
    op.create_unique_constraint(
        "uq_task_versions_key_version", "task_versions", ["stable_key", "version"]
    )
    op.drop_constraint("ck_task_versions_attachment_size", "task_versions", type_="check")
    op.drop_constraint("ck_task_versions_feedback_sla", "task_versions", type_="check")
    op.drop_constraint("ck_task_versions_estimated_duration", "task_versions", type_="check")
    op.drop_constraint("ck_task_versions_positive_version", "task_versions", type_="check")
    op.drop_constraint("uq_task_versions_id_definition", "task_versions", type_="unique")
    op.drop_constraint("uq_task_versions_definition_version", "task_versions", type_="unique")
    op.drop_index("ix_task_versions_task_definition_id", table_name="task_versions")
    op.drop_index("ix_task_versions_organization_id", table_name="task_versions")
    op.drop_constraint("fk_task_versions_reviewed_by", "task_versions", type_="foreignkey")
    op.drop_constraint("fk_task_versions_published_by", "task_versions", type_="foreignkey")
    op.drop_constraint("fk_task_versions_definition", "task_versions", type_="foreignkey")
    op.drop_constraint("fk_task_versions_organization", "task_versions", type_="foreignkey")
    for column_name in (
        "reviewed_by",
        "published_by",
        "audience",
        "sensitivity",
        "feedback_sla_business_days",
        "reviewer_role",
        "rubric_version",
        "estimated_duration_minutes",
        "reference_materials",
        "max_attachment_size_bytes",
        "allowed_attachment_types",
        "required_deliverables",
        "learner_outcome",
        "task_definition_id",
        "organization_id",
    ):
        op.drop_column("task_versions", column_name)
    op.drop_table("task_definitions")
