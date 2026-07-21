"""Add scoped reviewer workbench data and immutable evaluation history.

Revision ID: 0007_reviewer_workbench
Revises: 0006_submission_attachments
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_reviewer_workbench"
down_revision = "0006_submission_attachments"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("reviews", sa.Column("submission_id", UUID, nullable=True))
    op.add_column("reviews", sa.Column("assigned_at", TIMESTAMP, nullable=True))
    op.add_column("reviews", sa.Column("started_at", TIMESTAMP, nullable=True))
    op.add_column("reviews", sa.Column("finalized_at", TIMESTAMP, nullable=True))
    op.execute(
        """
        UPDATE reviews AS r
        SET submission_id = sv.submission_id,
            assigned_at = sv.created_at,
            started_at = CASE
                WHEN r.status IN ('IN_REVIEW', 'FINALIZED') THEN sv.created_at
                ELSE NULL
            END,
            finalized_at = CASE
                WHEN r.status = 'FINALIZED' THEN (
                    SELECT e.created_at
                    FROM evaluations AS e
                    WHERE e.review_id = r.id
                )
                ELSE NULL
            END
        FROM submission_versions AS sv
        WHERE sv.id = r.submission_version_id
        """
    )
    op.alter_column("reviews", "submission_id", nullable=False)
    op.alter_column(
        "reviews", "assigned_at", nullable=False, server_default=sa.func.now()
    )
    op.create_foreign_key(
        "fk_reviews_assignment_organization",
        "reviews",
        "assignments",
        ["assignment_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_reviews_submission_scope",
        "reviews",
        "submissions",
        ["submission_id", "organization_id", "assignment_id"],
        ["id", "organization_id", "assignment_id"],
    )
    op.create_foreign_key(
        "fk_reviews_submission_version",
        "reviews",
        "submission_versions",
        ["submission_version_id", "submission_id"],
        ["id", "submission_id"],
    )
    op.create_foreign_key(
        "fk_reviews_reviewer_organization",
        "reviews",
        "users",
        ["reviewer_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_unique_constraint(
        "uq_reviews_fixed_scope",
        "reviews",
        [
            "id",
            "organization_id",
            "assignment_id",
            "submission_id",
            "submission_version_id",
            "reviewer_id",
        ],
    )
    op.create_check_constraint(
        "ck_reviews_positive_revision", "reviews", "revision >= 1"
    )
    op.create_check_constraint(
        "ck_reviews_status_timestamps",
        "reviews",
        "(status = 'ASSIGNED' AND started_at IS NULL AND finalized_at IS NULL) "
        "OR (status = 'IN_REVIEW' AND started_at IS NOT NULL AND finalized_at IS NULL) "
        "OR (status = 'FINALIZED' AND started_at IS NOT NULL AND finalized_at IS NOT NULL)",
    )
    op.create_index(
        "ix_reviews_reviewer_status_assigned",
        "reviews",
        ["reviewer_id", "status", "assigned_at"],
    )

    op.add_column("evaluations", sa.Column("organization_id", UUID, nullable=True))
    op.add_column("evaluations", sa.Column("assignment_id", UUID, nullable=True))
    op.add_column("evaluations", sa.Column("submission_id", UUID, nullable=True))
    op.add_column(
        "evaluations", sa.Column("submission_version_id", UUID, nullable=True)
    )
    op.add_column("evaluations", sa.Column("reviewer_id", UUID, nullable=True))
    op.add_column("evaluations", sa.Column("review_revision", sa.Integer(), nullable=True))
    op.add_column("evaluations", sa.Column("structured_feedback", sa.JSON(), nullable=True))
    op.add_column(
        "evaluations",
        sa.Column(
            "feedback_structure_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE evaluations AS e
        SET organization_id = r.organization_id,
            assignment_id = r.assignment_id,
            submission_id = r.submission_id,
            submission_version_id = r.submission_version_id,
            reviewer_id = r.reviewer_id,
            review_revision = GREATEST(r.revision - 1, 1),
            feedback_structure_version = 0,
            structured_feedback = NULL
        FROM reviews AS r
        WHERE r.id = e.review_id
        """
    )
    for column in (
        "organization_id",
        "assignment_id",
        "submission_id",
        "submission_version_id",
        "reviewer_id",
        "review_revision",
    ):
        op.alter_column("evaluations", column, nullable=False)
    op.create_foreign_key(
        "fk_evaluations_review_fixed_scope",
        "evaluations",
        "reviews",
        [
            "review_id",
            "organization_id",
            "assignment_id",
            "submission_id",
            "submission_version_id",
            "reviewer_id",
        ],
        [
            "id",
            "organization_id",
            "assignment_id",
            "submission_id",
            "submission_version_id",
            "reviewer_id",
        ],
    )
    op.create_check_constraint(
        "ck_evaluations_reviewer_is_actor",
        "evaluations",
        "created_by = reviewer_id",
    )
    op.create_check_constraint(
        "ck_evaluations_positive_review_revision",
        "evaluations",
        "review_revision >= 1",
    )
    op.create_check_constraint(
        "ck_evaluations_feedback_structure",
        "evaluations",
        "(feedback_structure_version = 0 AND structured_feedback IS NULL) "
        "OR (feedback_structure_version = 1 AND structured_feedback IS NOT NULL)",
    )
    op.create_index(
        "ix_evaluations_organization_id", "evaluations", ["organization_id"]
    )

    op.execute(
        """
        CREATE FUNCTION protect_review_history() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Review rows are immutable history';
            END IF;
            IF OLD.status = 'FINALIZED' THEN
                RAISE EXCEPTION 'Finalized Review rows are immutable';
            END IF;
            IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.assignment_id IS DISTINCT FROM OLD.assignment_id
               OR NEW.submission_id IS DISTINCT FROM OLD.submission_id
               OR NEW.submission_version_id IS DISTINCT FROM OLD.submission_version_id
               OR NEW.reviewer_id IS DISTINCT FROM OLD.reviewer_id
               OR NEW.assigned_at IS DISTINCT FROM OLD.assigned_at THEN
                RAISE EXCEPTION 'Review fixed references are immutable';
            END IF;
            IF NEW.revision <> OLD.revision + 1 THEN
                RAISE EXCEPTION 'Review revision must increase by one';
            END IF;
            IF OLD.status = 'ASSIGNED' AND NEW.status <> 'IN_REVIEW' THEN
                RAISE EXCEPTION 'Invalid Review state transition';
            END IF;
            IF OLD.status = 'IN_REVIEW' AND NEW.status <> 'FINALIZED' THEN
                RAISE EXCEPTION 'Invalid Review state transition';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_protect_review_history
        BEFORE UPDATE OR DELETE ON reviews
        FOR EACH ROW EXECUTE FUNCTION protect_review_history()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_evaluation_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Evaluation rows are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_reject_evaluation_mutation
        BEFORE UPDATE OR DELETE ON evaluations
        FOR EACH ROW EXECUTE FUNCTION reject_evaluation_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_reject_evaluation_mutation ON evaluations")
    op.execute("DROP FUNCTION reject_evaluation_mutation")
    op.execute("DROP TRIGGER trg_protect_review_history ON reviews")
    op.execute("DROP FUNCTION protect_review_history")

    op.drop_index("ix_evaluations_organization_id", table_name="evaluations")
    op.drop_constraint(
        "ck_evaluations_feedback_structure", "evaluations", type_="check"
    )
    op.drop_constraint(
        "ck_evaluations_positive_review_revision", "evaluations", type_="check"
    )
    op.drop_constraint(
        "ck_evaluations_reviewer_is_actor", "evaluations", type_="check"
    )
    op.drop_constraint(
        "fk_evaluations_review_fixed_scope", "evaluations", type_="foreignkey"
    )
    for column in (
        "feedback_structure_version",
        "structured_feedback",
        "review_revision",
        "reviewer_id",
        "submission_version_id",
        "submission_id",
        "assignment_id",
        "organization_id",
    ):
        op.drop_column("evaluations", column)

    op.drop_index("ix_reviews_reviewer_status_assigned", table_name="reviews")
    op.drop_constraint("ck_reviews_status_timestamps", "reviews", type_="check")
    op.drop_constraint("ck_reviews_positive_revision", "reviews", type_="check")
    op.drop_constraint("uq_reviews_fixed_scope", "reviews", type_="unique")
    op.drop_constraint(
        "fk_reviews_reviewer_organization", "reviews", type_="foreignkey"
    )
    op.drop_constraint("fk_reviews_submission_version", "reviews", type_="foreignkey")
    op.drop_constraint("fk_reviews_submission_scope", "reviews", type_="foreignkey")
    op.drop_constraint(
        "fk_reviews_assignment_organization", "reviews", type_="foreignkey"
    )
    for column in ("finalized_at", "started_at", "assigned_at", "submission_id"):
        op.drop_column("reviews", column)
