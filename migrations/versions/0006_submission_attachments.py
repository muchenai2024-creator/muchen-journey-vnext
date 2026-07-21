"""Add immutable submissions, recoverable drafts, and isolated attachments.

Revision ID: 0006_submission_attachments
Revises: 0005_task_publish_evidence
"""

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0006_submission_attachments"
down_revision = "0005_task_publish_evidence"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def _backfill_submission_containers() -> None:
    bind = op.get_bind()
    assignment_ids = bind.execute(
        sa.text("SELECT DISTINCT assignment_id FROM submission_versions ORDER BY assignment_id")
    ).scalars()
    for assignment_id in assignment_ids:
        submission_id = uuid.uuid4()
        row = bind.execute(
            sa.text(
                """
                SELECT organization_id,
                       (SELECT max(version_no)
                        FROM submission_versions
                        WHERE assignment_id = assignments.id) AS current_version_no
                FROM assignments
                WHERE id = :assignment_id
                """
            ),
            {"assignment_id": assignment_id},
        ).mappings().one()
        bind.execute(
            sa.text(
                """
                INSERT INTO submissions
                    (id, organization_id, assignment_id, current_version_no)
                VALUES
                    (:id, :organization_id, :assignment_id, :current_version_no)
                """
            ),
            {
                "id": submission_id,
                "organization_id": row["organization_id"],
                "assignment_id": assignment_id,
                "current_version_no": row["current_version_no"],
            },
        )
        bind.execute(
            sa.text(
                "UPDATE submission_versions SET submission_id = :submission_id "
                "WHERE assignment_id = :assignment_id"
            ),
            {"submission_id": submission_id, "assignment_id": assignment_id},
        )


def upgrade() -> None:
    op.create_unique_constraint("uq_users_id_organization", "users", ["id", "organization_id"])
    op.create_unique_constraint(
        "uq_assignments_id_organization", "assignments", ["id", "organization_id"]
    )

    op.create_table(
        "submissions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("current_version_no", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_submissions_assignment_organization",
        ),
        sa.CheckConstraint(
            "current_version_no >= 0", name="ck_submissions_nonnegative_current_version"
        ),
        sa.UniqueConstraint("assignment_id", name="uq_submissions_assignment"),
        sa.UniqueConstraint("id", "organization_id", name="uq_submissions_id_organization"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "assignment_id",
            name="uq_submissions_id_organization_assignment",
        ),
    )
    op.create_index("ix_submissions_organization_id", "submissions", ["organization_id"])

    op.add_column("submission_versions", sa.Column("submission_id", UUID, nullable=True))
    _backfill_submission_containers()
    op.alter_column("submission_versions", "submission_id", nullable=False)
    op.create_foreign_key(
        "fk_submission_versions_submission",
        "submission_versions",
        "submissions",
        ["submission_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_submission_versions_submission_version",
        "submission_versions",
        ["submission_id", "version_no"],
    )
    op.create_unique_constraint(
        "uq_submission_versions_id_submission",
        "submission_versions",
        ["id", "submission_id"],
    )
    op.create_check_constraint(
        "ck_submission_versions_positive_version", "submission_versions", "version_no >= 1"
    )
    op.drop_constraint(
        "uq_submission_assignment_version", "submission_versions", type_="unique"
    )
    op.drop_index("ix_submission_versions_assignment_id", table_name="submission_versions")
    op.drop_constraint(
        "submission_versions_assignment_id_fkey", "submission_versions", type_="foreignkey"
    )
    op.drop_column("submission_versions", "assignment_id")
    op.create_index(
        "ix_submission_versions_submission_id", "submission_versions", ["submission_id"]
    )

    op.create_table(
        "submission_drafts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("owner_id", UUID, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("attachment_ids", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_submission_drafts_assignment_organization",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_submission_drafts_owner_organization",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_submission_drafts_positive_revision"),
        sa.UniqueConstraint("assignment_id", name="uq_submission_drafts_assignment"),
    )
    op.create_index(
        "ix_submission_drafts_organization_id", "submission_drafts", ["organization_id"]
    )

    op.create_table(
        "attachments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("owner_id", UUID, nullable=False),
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("original_filename", sa.String(180), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False, unique=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("scan_status", sa.String(24), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("uploaded_at", TIMESTAMP, nullable=True),
        sa.Column("completed_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_attachments_owner_organization",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_attachments_assignment_organization",
        ),
        sa.CheckConstraint(
            "purpose IN ('SUBMISSION_EVIDENCE')", name="ck_attachments_purpose"
        ),
        sa.CheckConstraint(
            "content_type IN ('text/plain', 'application/pdf', 'image/png', 'image/jpeg')",
            name="ck_attachments_content_type",
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 5242880", name="ck_attachments_size"
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'", name="ck_attachments_sha256"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_UPLOAD', 'UPLOADED', 'READY', 'REJECTED', 'DELETED')",
            name="ck_attachments_status",
        ),
        sa.CheckConstraint(
            "scan_status IN ('PENDING', 'LOCAL_CLEAN', 'LOCAL_REJECTED')",
            name="ck_attachments_scan_status",
        ),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "assignment_id",
            name="uq_attachments_id_organization_assignment",
        ),
    )
    op.create_index("ix_attachments_organization_id", "attachments", ["organization_id"])
    op.create_index("ix_attachments_owner_id", "attachments", ["owner_id"])
    op.create_index("ix_attachments_assignment_id", "attachments", ["assignment_id"])

    op.create_table(
        "submission_version_attachments",
        sa.Column("submission_id", UUID, nullable=False),
        sa.Column("submission_version_id", UUID, nullable=False),
        sa.Column("attachment_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_version_id", "submission_id"],
            ["submission_versions.id", "submission_versions.submission_id"],
            name="fk_submission_attachment_version_submission",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id", "organization_id", "assignment_id"],
            ["submissions.id", "submissions.organization_id", "submissions.assignment_id"],
            name="fk_submission_attachment_submission_scope",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id", "organization_id", "assignment_id"],
            ["attachments.id", "attachments.organization_id", "attachments.assignment_id"],
            name="fk_submission_attachment_file_scope",
        ),
        sa.CheckConstraint("position >= 1", name="ck_submission_attachment_position"),
        sa.PrimaryKeyConstraint("submission_version_id", "attachment_id"),
        sa.UniqueConstraint("attachment_id", name="uq_submission_attachment_file"),
        sa.UniqueConstraint(
            "submission_version_id", "position", name="uq_submission_attachment_position"
        ),
    )

    op.execute(
        """
        CREATE FUNCTION reject_submission_version_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'SubmissionVersion rows are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER submission_versions_immutable
        BEFORE UPDATE OR DELETE ON submission_versions
        FOR EACH ROW EXECUTE FUNCTION reject_submission_version_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_submission_attachment_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'SubmissionVersion attachment links are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER submission_version_attachments_immutable
        BEFORE UPDATE OR DELETE ON submission_version_attachments
        FOR EACH ROW EXECUTE FUNCTION reject_submission_attachment_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_bound_attachment_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM submission_version_attachments
                WHERE attachment_id = OLD.id
            ) THEN
                RAISE EXCEPTION 'Bound Attachment rows are immutable';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER bound_attachments_immutable
        BEFORE UPDATE OR DELETE ON attachments
        FOR EACH ROW EXECUTE FUNCTION reject_bound_attachment_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS bound_attachments_immutable ON attachments")
    op.execute("DROP FUNCTION IF EXISTS reject_bound_attachment_mutation()")
    op.execute(
        "DROP TRIGGER IF EXISTS submission_version_attachments_immutable "
        "ON submission_version_attachments"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_submission_attachment_mutation()")
    op.execute("DROP TRIGGER IF EXISTS submission_versions_immutable ON submission_versions")
    op.execute("DROP FUNCTION IF EXISTS reject_submission_version_mutation()")

    op.drop_table("submission_version_attachments")
    op.drop_table("attachments")
    op.drop_table("submission_drafts")

    op.add_column("submission_versions", sa.Column("assignment_id", UUID, nullable=True))
    op.execute(
        """
        UPDATE submission_versions AS sv
        SET assignment_id = s.assignment_id
        FROM submissions AS s
        WHERE s.id = sv.submission_id
        """
    )
    op.alter_column("submission_versions", "assignment_id", nullable=False)
    op.create_foreign_key(
        "submission_versions_assignment_id_fkey",
        "submission_versions",
        "assignments",
        ["assignment_id"],
        ["id"],
    )
    op.create_index(
        "ix_submission_versions_assignment_id", "submission_versions", ["assignment_id"]
    )
    op.create_unique_constraint(
        "uq_submission_assignment_version",
        "submission_versions",
        ["assignment_id", "version_no"],
    )
    op.drop_constraint(
        "ck_submission_versions_positive_version", "submission_versions", type_="check"
    )
    op.drop_constraint(
        "uq_submission_versions_id_submission", "submission_versions", type_="unique"
    )
    op.drop_constraint(
        "uq_submission_versions_submission_version", "submission_versions", type_="unique"
    )
    op.drop_index("ix_submission_versions_submission_id", table_name="submission_versions")
    op.drop_constraint(
        "fk_submission_versions_submission", "submission_versions", type_="foreignkey"
    )
    op.drop_column("submission_versions", "submission_id")
    op.drop_table("submissions")

    op.drop_constraint("uq_assignments_id_organization", "assignments", type_="unique")
    op.drop_constraint("uq_users_id_organization", "users", type_="unique")
