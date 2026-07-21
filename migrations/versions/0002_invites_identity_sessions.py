"""Add WP-01 invitations, vNext identities, and independent sessions.

Revision ID: 0002_invites_identity_sessions
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_invites_identity_sessions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.drop_constraint("ck_users_status", "users", type_="check")
    op.create_check_constraint(
        "ck_users_status", "users", "status IN ('PENDING_IDENTITY', 'ACTIVE', 'DISABLED')"
    )
    op.drop_constraint("ck_enrollments_status", "enrollments", type_="check")
    op.create_check_constraint(
        "ck_enrollments_status",
        "enrollments",
        "status IN ('PENDING_IDENTITY', 'ACTIVE', 'COMPLETED', 'CANCELLED')",
    )
    op.create_index(
        "uq_enrollments_active_learner",
        "enrollments",
        ["organization_id", "learner_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING_IDENTITY', 'ACTIVE')"),
    )
    op.create_table(
        "external_identities",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(180), nullable=False),
        sa.Column("verified_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "provider", "subject", name="uq_external_identity_provider_subject"
        ),
    )
    op.create_index("ix_external_identities_organization_id", "external_identities", ["organization_id"])
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"])
    op.create_table(
        "invites",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("purpose", sa.String(200), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("reviewer_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_version_id", UUID, sa.ForeignKey("task_versions.id"), nullable=False),
        sa.Column("target_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("consumed_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("consumed_at", TIMESTAMP, nullable=True),
        sa.Column("revoked_at", TIMESTAMP, nullable=True),
        sa.Column("revoke_reason", sa.String(500), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role = 'LEARNER'", name="ck_invites_wp01_role"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'CONSUMED', 'REVOKED', 'EXPIRED')",
            name="ck_invites_status",
        ),
    )
    op.create_index("ix_invites_organization_id", "invites", ["organization_id"])
    op.create_index("ix_invites_status", "invites", ["status"])
    op.create_index("ix_invites_expires_at", "invites", ["expires_at"])
    op.create_table(
        "join_contexts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("invite_id", UUID, sa.ForeignKey("invites.id"), nullable=False, unique=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_user", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'REVOKED')", name="ck_join_contexts_status"
        ),
    )
    op.create_index("ix_join_contexts_expires_at", "join_contexts", ["expires_at"])
    op.create_table(
        "identity_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            "role IN ('LEARNER', 'REVIEWER', 'OPERATOR')", name="ck_identity_sessions_role"
        ),
    )
    op.create_index("ix_identity_sessions_organization_id", "identity_sessions", ["organization_id"])
    op.create_index("ix_identity_sessions_user_id", "identity_sessions", ["user_id"])
    op.create_index("ix_identity_sessions_expires_at", "identity_sessions", ["expires_at"])
    op.create_table(
        "audit_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("actor_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", UUID, nullable=True),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_entries_organization_id", "audit_entries", ["organization_id"])
    op.create_index("ix_audit_entries_action", "audit_entries", ["action"])
    op.create_index("ix_audit_entries_request_id", "audit_entries", ["request_id"])
    op.create_table(
        "auth_rate_limits",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("scope", sa.String(60), nullable=False),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("window_started_at", TIMESTAMP, nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
        sa.UniqueConstraint(
            "scope", "subject_hash", "window_started_at", name="uq_auth_rate_limit_window"
        ),
    )


def downgrade() -> None:
    for table in (
        "auth_rate_limits",
        "audit_entries",
        "identity_sessions",
        "join_contexts",
        "invites",
        "external_identities",
    ):
        op.drop_table(table)
    op.drop_index("uq_enrollments_active_learner", table_name="enrollments")
