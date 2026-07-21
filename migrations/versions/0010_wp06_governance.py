"""Add controlled operations, import ledger, and worker health facts.

Revision ID: 0010_wp06_governance
Revises: 0009_notification_scope
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID


revision = "0010_wp06_governance"
down_revision = "0009_notification_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_name", sa.String(length=80), primary_key=True),
        sa.Column("release", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("last_seen_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('RUNNING', 'IDLE')", name="ck_worker_heartbeats_status"),
    )
    op.create_table(
        "import_batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", UUID(as_uuid=True), nullable=False),
        sa.Column("package_checksum", sa.String(length=64), nullable=False),
        sa.Column("source_revision", sa.String(length=120), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("replayed_count", sa.Integer(), nullable=False),
        sa.Column("quarantined_count", sa.Integer(), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("id", "organization_id", name="uq_import_batches_fixed_scope"),
        sa.UniqueConstraint("package_id", name="uq_import_batches_package_id"),
        sa.UniqueConstraint("package_checksum", name="uq_import_batches_checksum"),
        sa.CheckConstraint("schema_version = 1", name="ck_import_batches_schema_v1"),
        sa.CheckConstraint(
            "status IN ('APPLIED', 'APPLIED_WITH_QUARANTINE')",
            name="ck_import_batches_status",
        ),
        sa.CheckConstraint(
            "record_count >= 0 AND imported_count >= 0 AND replayed_count >= 0 "
            "AND quarantined_count >= 0",
            name="ck_import_batches_nonnegative_counts",
        ),
    )
    op.create_index("ix_import_batches_organization_id", "import_batches", ["organization_id"])
    op.create_table(
        "import_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_namespace", sa.String(length=80), nullable=False),
        sa.Column("source_key", sa.String(length=120), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["batch_id", "organization_id"],
            ["import_batches.id", "import_batches.organization_id"],
            name="fk_import_records_batch_scope",
        ),
        sa.UniqueConstraint("batch_id", "source_key", name="uq_import_records_batch_key"),
        sa.CheckConstraint(
            "status IN ('IMPORTED', 'REPLAYED', 'QUARANTINED')",
            name="ck_import_records_status",
        ),
    )
    op.create_index("ix_import_records_batch_id", "import_records", ["batch_id"])
    op.create_index("ix_import_records_organization_id", "import_records", ["organization_id"])
    op.create_index(
        "ix_import_records_source_lookup",
        "import_records",
        ["organization_id", "source_namespace", "source_key", "created_at"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_import_history_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Import history is immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_reject_import_batch_mutation
        BEFORE UPDATE OR DELETE ON import_batches
        FOR EACH ROW EXECUTE FUNCTION reject_import_history_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_reject_import_record_mutation
        BEFORE UPDATE OR DELETE ON import_records
        FOR EACH ROW EXECUTE FUNCTION reject_import_history_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_reject_import_record_mutation ON import_records")
    op.execute("DROP TRIGGER trg_reject_import_batch_mutation ON import_batches")
    op.execute("DROP FUNCTION reject_import_history_mutation")
    op.drop_index("ix_import_records_source_lookup", table_name="import_records")
    op.drop_index("ix_import_records_organization_id", table_name="import_records")
    op.drop_index("ix_import_records_batch_id", table_name="import_records")
    op.drop_table("import_records")
    op.drop_index("ix_import_batches_organization_id", table_name="import_batches")
    op.drop_table("import_batches")
    op.drop_table("worker_heartbeats")
