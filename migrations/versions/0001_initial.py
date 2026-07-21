"""Create the vNext walking-skeleton schema.

Revision ID: 0001_initial
Revises: None
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING_IDENTITY', 'ACTIVE', 'DISABLED')", name="ck_users_status"
        ),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_table(
        "role_assignments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.CheckConstraint("role IN ('LEARNER', 'REVIEWER', 'OPERATOR')", name="ck_role_assignments_role"),
        sa.UniqueConstraint("user_id", "role", name="uq_role_assignments_user_role"),
    )
    op.create_index("ix_role_assignments_organization_id", "role_assignments", ["organization_id"])
    op.create_index("ix_role_assignments_user_id", "role_assignments", ["user_id"])
    op.create_table(
        "task_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("stable_key", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("instructions", sa.JSON(), nullable=False),
        sa.Column("completion_criteria", sa.JSON(), nullable=False),
        sa.Column("rubric", sa.JSON(), nullable=False),
        sa.Column("published_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("stable_key", "version", name="uq_task_versions_key_version"),
    )
    op.create_table(
        "enrollments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("learner_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewer_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('PENDING_IDENTITY', 'ACTIVE', 'COMPLETED', 'CANCELLED')",
            name="ck_enrollments_status",
        ),
    )
    op.create_index("ix_enrollments_organization_id", "enrollments", ["organization_id"])
    op.create_index("ix_enrollments_learner_id", "enrollments", ["learner_id"])
    op.create_index("ix_enrollments_reviewer_id", "enrollments", ["reviewer_id"])
    op.create_table(
        "assignments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id"), nullable=False),
        sa.Column("task_version_id", UUID, sa.ForeignKey("task_versions.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('AVAILABLE', 'IN_PROGRESS', 'SUBMITTED', 'IN_REVIEW', 'NEEDS_REVISION', 'COMPLETED')",
            name="ck_assignments_status",
        ),
    )
    op.create_index("ix_assignments_organization_id", "assignments", ["organization_id"])
    op.create_index("ix_assignments_enrollment_id", "assignments", ["enrollment_id"])
    op.create_table(
        "submission_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("assignment_id", UUID, sa.ForeignKey("assignments.id"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("assignment_id", "version_no", name="uq_submission_assignment_version"),
    )
    op.create_index("ix_submission_versions_assignment_id", "submission_versions", ["assignment_id"])
    op.create_table(
        "reviews",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("assignment_id", UUID, sa.ForeignKey("assignments.id"), nullable=False),
        sa.Column("submission_version_id", UUID, sa.ForeignKey("submission_versions.id"), nullable=False),
        sa.Column("reviewer_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("status IN ('ASSIGNED', 'IN_REVIEW', 'FINALIZED')", name="ck_reviews_status"),
        sa.UniqueConstraint("submission_version_id", name="uq_review_submission_version"),
    )
    op.create_index("ix_reviews_organization_id", "reviews", ["organization_id"])
    op.create_index("ix_reviews_assignment_id", "reviews", ["assignment_id"])
    op.create_index("ix_reviews_reviewer_id", "reviews", ["reviewer_id"])
    op.create_table(
        "evaluations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("review_id", UUID, sa.ForeignKey("reviews.id"), nullable=False, unique=True),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("rubric_scores", sa.JSON(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("decision IN ('PASS', 'REVISION_REQUIRED')", name="ck_evaluations_decision"),
    )
    op.create_table(
        "outcomes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id"), nullable=False, unique=True),
        sa.Column("source_evaluation_id", UUID, sa.ForeignKey("evaluations.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=False),
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", UUID, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("occurred_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint("status IN ('PENDING', 'PROCESSED')", name="ck_outbox_events_status"),
    )
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
    op.create_table(
        "idempotency_records",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("actor_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("command", sa.String(120), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("actor_id", "command", "key", name="uq_idempotency_actor_command_key"),
    )
    op.create_index("ix_idempotency_records_actor_id", "idempotency_records", ["actor_id"])


def downgrade() -> None:
    for table in (
        "idempotency_records",
        "outbox_events",
        "outcomes",
        "evaluations",
        "reviews",
        "submission_versions",
        "assignments",
        "enrollments",
        "task_versions",
        "role_assignments",
        "users",
        "organizations",
    ):
        op.drop_table(table)
