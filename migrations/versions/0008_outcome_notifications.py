"""Add immutable outcomes, handoffs, notification delivery, and worker retry facts.

Revision ID: 0008_outcome_notifications
Revises: 0007_reviewer_workbench
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0008_outcome_notifications"
down_revision = "0007_reviewer_workbench"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_enrollments_fixed_owner_scope",
        "enrollments",
        ["id", "organization_id", "learner_id"],
    )
    op.create_unique_constraint(
        "uq_evaluations_outcome_scope",
        "evaluations",
        ["id", "organization_id", "assignment_id"],
    )

    op.alter_column("outcomes", "next_step", new_column_name="summary")
    op.add_column("outcomes", sa.Column("organization_id", UUID, nullable=True))
    op.add_column("outcomes", sa.Column("learner_id", UUID, nullable=True))
    op.add_column("outcomes", sa.Column("assignment_id", UUID, nullable=True))
    op.add_column("outcomes", sa.Column("created_at", TIMESTAMP, nullable=True))
    op.execute(
        """
        UPDATE outcomes AS o
        SET organization_id = e.organization_id,
            learner_id = e.learner_id,
            assignment_id = ev.assignment_id,
            created_at = ev.created_at
        FROM enrollments AS e, evaluations AS ev
        WHERE e.id = o.enrollment_id
          AND ev.id = o.source_evaluation_id
        """
    )
    for column in ("organization_id", "learner_id", "assignment_id", "created_at"):
        op.alter_column("outcomes", column, nullable=False)
    op.alter_column("outcomes", "created_at", server_default=sa.func.now())
    op.create_foreign_key(
        "fk_outcomes_enrollment_owner_scope",
        "outcomes",
        "enrollments",
        ["enrollment_id", "organization_id", "learner_id"],
        ["id", "organization_id", "learner_id"],
    )
    op.create_foreign_key(
        "fk_outcomes_evaluation_scope",
        "outcomes",
        "evaluations",
        ["source_evaluation_id", "organization_id", "assignment_id"],
        ["id", "organization_id", "assignment_id"],
    )
    op.create_unique_constraint(
        "uq_outcomes_fixed_scope",
        "outcomes",
        ["id", "organization_id", "enrollment_id", "source_evaluation_id", "learner_id"],
    )
    op.create_unique_constraint(
        "uq_outcomes_handoff_scope",
        "outcomes",
        ["id", "organization_id", "enrollment_id", "source_evaluation_id"],
    )
    op.create_unique_constraint(
        "uq_outcomes_recipient_scope",
        "outcomes",
        ["id", "organization_id", "learner_id"],
    )
    op.create_unique_constraint("uq_outcomes_assignment", "outcomes", ["assignment_id"])
    op.create_check_constraint(
        "ck_outcomes_handoff_ready", "outcomes", "status = 'HANDOFF_READY'"
    )
    op.create_index("ix_outcomes_organization_learner", "outcomes", ["organization_id", "learner_id"])

    op.create_table(
        "handoffs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("outcome_id", UUID, nullable=False),
        sa.Column("source_evaluation_id", UUID, nullable=False),
        sa.Column("owner_user_id", UUID, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("next_step_code", sa.String(80), nullable=False),
        sa.Column("next_step_title", sa.String(240), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["outcome_id", "organization_id", "enrollment_id", "source_evaluation_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.enrollment_id", "outcomes.source_evaluation_id"],
            name="fk_handoffs_outcome_fixed_scope",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_handoffs_owner_organization",
        ),
        sa.UniqueConstraint("outcome_id", name="uq_handoffs_outcome"),
        sa.UniqueConstraint("enrollment_id", name="uq_handoffs_enrollment"),
        sa.UniqueConstraint("source_evaluation_id", name="uq_handoffs_evaluation"),
        sa.CheckConstraint("status = 'READY'", name="ck_handoffs_ready"),
        sa.CheckConstraint(
            "next_step_code = 'CONFIRM_HANDOFF'", name="ck_handoffs_next_step"
        ),
    )
    op.create_index("ix_handoffs_organization_enrollment", "handoffs", ["organization_id", "enrollment_id"])

    bind = op.get_bind()
    existing_outcomes = bind.execute(
        sa.text(
            """
            SELECT o.id, o.organization_id, o.enrollment_id, o.source_evaluation_id,
                   o.summary, o.created_at, e.reviewer_id
            FROM outcomes AS o
            JOIN enrollments AS e ON e.id = o.enrollment_id
            """
        )
    ).mappings()
    for row in existing_outcomes:
        bind.execute(
            sa.text(
                """
                INSERT INTO handoffs (
                    id, organization_id, enrollment_id, outcome_id,
                    source_evaluation_id, owner_user_id, status, title,
                    next_step_code, next_step_title, instructions, created_at
                ) VALUES (
                    :id, :organization_id, :enrollment_id, :outcome_id,
                    :source_evaluation_id, :owner_user_id, 'READY',
                    '探索营交接已准备', 'CONFIRM_HANDOFF',
                    '与交接责任人确认下一步', :instructions, :created_at
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "organization_id": row["organization_id"],
                "enrollment_id": row["enrollment_id"],
                "outcome_id": row["id"],
                "source_evaluation_id": row["source_evaluation_id"],
                "owner_user_id": row["reviewer_id"],
                "instructions": row["summary"],
                "created_at": row["created_at"],
            },
        )

    op.drop_constraint("ck_outbox_events_status", "outbox_events", type_="check")
    op.add_column("outbox_events", sa.Column("organization_id", UUID, nullable=True))
    op.add_column("outbox_events", sa.Column("owner_id", UUID, nullable=True))
    op.add_column("outbox_events", sa.Column("actor_id", UUID, nullable=True))
    op.add_column("outbox_events", sa.Column("request_id", sa.String(100), nullable=True))
    op.add_column(
        "outbox_events",
        sa.Column("payload_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "outbox_events",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("outbox_events", sa.Column("next_attempt_at", TIMESTAMP, nullable=True))
    op.add_column("outbox_events", sa.Column("locked_at", TIMESTAMP, nullable=True))
    op.add_column("outbox_events", sa.Column("lock_token", UUID, nullable=True))
    op.add_column("outbox_events", sa.Column("last_error_code", sa.String(80), nullable=True))
    op.add_column("outbox_events", sa.Column("dedupe_key", sa.String(200), nullable=True))
    op.execute("UPDATE outbox_events SET status = 'SENT' WHERE status = 'PROCESSED'")
    op.execute(
        "UPDATE outbox_events SET dedupe_key = 'legacy:' || id::text WHERE dedupe_key IS NULL"
    )
    op.execute(
        "UPDATE outbox_events SET next_attempt_at = occurred_at WHERE status = 'PENDING'"
    )
    op.create_foreign_key(
        "fk_outbox_events_organization", "outbox_events", "organizations", ["organization_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_outbox_events_owner", "outbox_events", "users", ["owner_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_outbox_events_actor", "outbox_events", "users", ["actor_id"], ["id"]
    )
    op.create_unique_constraint("uq_outbox_events_dedupe_key", "outbox_events", ["dedupe_key"])
    op.create_check_constraint(
        "ck_outbox_events_status",
        "outbox_events",
        "status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED')",
    )
    op.create_check_constraint(
        "ck_outbox_events_attempt_count", "outbox_events", "attempt_count >= 0"
    )
    op.create_check_constraint(
        "ck_outbox_events_lock_state",
        "outbox_events",
        "(status = 'PROCESSING' AND locked_at IS NOT NULL AND lock_token IS NOT NULL) "
        "OR (status <> 'PROCESSING' AND locked_at IS NULL AND lock_token IS NULL)",
    )
    op.create_check_constraint(
        "ck_outbox_notification_scope",
        "outbox_events",
        "event_type <> 'notification.requested.v1' "
        "OR (organization_id IS NOT NULL AND owner_id IS NOT NULL AND dedupe_key IS NOT NULL)",
    )
    op.create_index(
        "ix_outbox_events_due", "outbox_events", ["status", "next_attempt_at", "occurred_at"]
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("event_id", UUID, nullable=False),
        sa.Column("outcome_id", UUID, nullable=False),
        sa.Column("recipient_user_id", UUID, nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("template_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", TIMESTAMP, nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("delivered_at", TIMESTAMP, nullable=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["outbox_events.id"], name="fk_notification_deliveries_event"),
        sa.ForeignKeyConstraint(
            ["outcome_id", "organization_id", "recipient_user_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.learner_id"],
            name="fk_notification_deliveries_outcome_recipient",
        ),
        sa.UniqueConstraint("event_id", name="uq_notification_deliveries_event"),
        sa.UniqueConstraint(
            "event_id", "recipient_user_id", "channel", "template_version",
            name="uq_notification_deliveries_dedupe",
        ),
        sa.CheckConstraint(
            "channel IN ('LOCAL_TEST', 'FEISHU', 'EMAIL')",
            name="ck_notification_deliveries_channel",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENDING', 'DELIVERED', 'RETRY_WAIT', 'DEAD')",
            name="ck_notification_deliveries_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_notification_deliveries_attempts"),
        sa.CheckConstraint(
            "(status = 'PENDING' AND attempt_count = 0 AND delivered_at IS NULL) "
            "OR (status = 'SENDING' AND attempt_count >= 1 AND delivered_at IS NULL) "
            "OR (status = 'DELIVERED' AND attempt_count >= 1 AND delivered_at IS NOT NULL) "
            "OR (status = 'RETRY_WAIT' AND attempt_count >= 1 AND next_attempt_at IS NOT NULL "
            "    AND last_error_code IS NOT NULL AND delivered_at IS NULL) "
            "OR (status = 'DEAD' AND attempt_count >= 1 AND next_attempt_at IS NULL "
            "    AND last_error_code IS NOT NULL AND delivered_at IS NULL)",
            name="ck_notification_deliveries_state_fields",
        ),
    )
    op.create_index(
        "ix_notification_deliveries_owner_status",
        "notification_deliveries",
        ["organization_id", "recipient_user_id", "status"],
    )

    op.create_table(
        "notification_attempts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("delivery_id", UUID, sa.ForeignKey("notification_deliveries.id"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("attempted_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("delivery_id", "attempt_number", name="uq_notification_attempt_number"),
        sa.CheckConstraint("attempt_number >= 1", name="ck_notification_attempt_positive"),
        sa.CheckConstraint(
            "status IN ('DELIVERED', 'FAILED_RETRYABLE', 'FAILED_FINAL', 'LEASE_EXPIRED')",
            name="ck_notification_attempt_status",
        ),
        sa.CheckConstraint(
            "(status = 'DELIVERED' AND error_code IS NULL) "
            "OR (status <> 'DELIVERED' AND error_code IS NOT NULL)",
            name="ck_notification_attempt_error",
        ),
    )
    op.create_index(
        "ix_notification_attempts_delivery_time",
        "notification_attempts",
        ["delivery_id", "attempted_at"],
    )

    op.create_table(
        "local_notification_receipts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("delivery_id", UUID, sa.ForeignKey("notification_deliveries.id"), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("delivery_id", name="uq_local_notification_receipt_delivery"),
        sa.UniqueConstraint("dedupe_key", name="uq_local_notification_receipt_dedupe"),
    )

    op.execute(
        """
        CREATE FUNCTION reject_wp05_immutable_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'WP-05 historical fact rows are immutable';
        END;
        $$
        """
    )
    for table in ("outcomes", "handoffs", "notification_attempts", "local_notification_receipts"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_wp05_immutable_mutation()
            """
        )


def downgrade() -> None:
    for table in ("local_notification_receipts", "notification_attempts", "handoffs", "outcomes"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_wp05_immutable_mutation")

    op.drop_table("local_notification_receipts")
    op.drop_index("ix_notification_attempts_delivery_time", table_name="notification_attempts")
    op.drop_table("notification_attempts")
    op.drop_index(
        "ix_notification_deliveries_owner_status", table_name="notification_deliveries"
    )
    op.drop_table("notification_deliveries")

    op.drop_index("ix_outbox_events_due", table_name="outbox_events")
    op.drop_constraint("ck_outbox_notification_scope", "outbox_events", type_="check")
    op.drop_constraint("ck_outbox_events_lock_state", "outbox_events", type_="check")
    op.drop_constraint("ck_outbox_events_attempt_count", "outbox_events", type_="check")
    op.drop_constraint("ck_outbox_events_status", "outbox_events", type_="check")
    op.drop_constraint("uq_outbox_events_dedupe_key", "outbox_events", type_="unique")
    op.drop_constraint("fk_outbox_events_actor", "outbox_events", type_="foreignkey")
    op.drop_constraint("fk_outbox_events_owner", "outbox_events", type_="foreignkey")
    op.drop_constraint("fk_outbox_events_organization", "outbox_events", type_="foreignkey")
    op.execute("UPDATE outbox_events SET status = 'PROCESSED' WHERE status <> 'PENDING'")
    for column in (
        "dedupe_key",
        "last_error_code",
        "lock_token",
        "locked_at",
        "next_attempt_at",
        "attempt_count",
        "payload_version",
        "request_id",
        "actor_id",
        "owner_id",
        "organization_id",
    ):
        op.drop_column("outbox_events", column)
    op.create_check_constraint(
        "ck_outbox_events_status",
        "outbox_events",
        "status IN ('PENDING', 'PROCESSED')",
    )

    op.drop_index("ix_handoffs_organization_enrollment", table_name="handoffs")
    op.drop_table("handoffs")

    op.drop_index("ix_outcomes_organization_learner", table_name="outcomes")
    op.drop_constraint("ck_outcomes_handoff_ready", "outcomes", type_="check")
    op.drop_constraint("uq_outcomes_assignment", "outcomes", type_="unique")
    op.drop_constraint("uq_outcomes_recipient_scope", "outcomes", type_="unique")
    op.drop_constraint("uq_outcomes_handoff_scope", "outcomes", type_="unique")
    op.drop_constraint("uq_outcomes_fixed_scope", "outcomes", type_="unique")
    op.drop_constraint("fk_outcomes_evaluation_scope", "outcomes", type_="foreignkey")
    op.drop_constraint("fk_outcomes_enrollment_owner_scope", "outcomes", type_="foreignkey")
    for column in ("created_at", "assignment_id", "learner_id", "organization_id"):
        op.drop_column("outcomes", column)
    op.alter_column("outcomes", "summary", new_column_name="next_step")

    op.drop_constraint(
        "uq_evaluations_outcome_scope", "evaluations", type_="unique"
    )
    op.drop_constraint(
        "uq_enrollments_fixed_owner_scope", "enrollments", type_="unique"
    )
