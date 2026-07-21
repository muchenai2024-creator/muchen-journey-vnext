"""Record source, change, and calibration evidence for each TaskVersion publish.

Revision ID: 0005_task_publish_evidence
Revises: 0004_task_contract_repair
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_task_publish_evidence"
down_revision = "0004_task_contract_repair"
branch_labels = None
depends_on = None


def _create_immutability_trigger() -> None:
    op.execute(
        """
        CREATE TRIGGER task_versions_immutable
        BEFORE UPDATE OR DELETE ON task_versions
        FOR EACH ROW EXECUTE FUNCTION reject_task_version_mutation()
        """
    )


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS task_versions_immutable ON task_versions")
    op.add_column("task_versions", sa.Column("content_source_notes", sa.JSON(), nullable=True))
    op.add_column("task_versions", sa.Column("change_summary", sa.Text(), nullable=True))
    op.add_column(
        "task_versions", sa.Column("reviewer_calibration_note", sa.Text(), nullable=True)
    )
    op.execute(
        """
        UPDATE task_versions
        SET content_source_notes = CAST(
                '["批准文档 03、04、05 与 15 中的 TSK-001 V1 合同"]' AS JSON
            ),
            change_summary = '从 walking skeleton 补齐 WP-02 不可变任务版本合同。',
            reviewer_calibration_note =
                '迁移本地 fixture Rubric；真人 Reviewer 校准仍为 NOT_RUN 门禁。'
        """
    )
    op.alter_column("task_versions", "content_source_notes", nullable=False)
    op.alter_column("task_versions", "change_summary", nullable=False)
    op.alter_column("task_versions", "reviewer_calibration_note", nullable=False)
    _create_immutability_trigger()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS task_versions_immutable ON task_versions")
    op.drop_column("task_versions", "reviewer_calibration_note")
    op.drop_column("task_versions", "change_summary")
    op.drop_column("task_versions", "content_source_notes")
    _create_immutability_trigger()
