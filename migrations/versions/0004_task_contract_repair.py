"""Repair pre-WP-02 skeleton rubric rows already migrated by early 0003 builds.

Revision ID: 0004_task_contract_repair
Revises: 0003_current_action_tasks
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "0004_task_contract_repair"
down_revision = "0003_current_action_tasks"
branch_labels = None
depends_on = None


def _dimension(
    key: str,
    title: str,
    purpose: str,
    evidence: str,
    meets: str,
    needs_work: str,
    prompt: str,
) -> dict[str, object]:
    return {
        "dimension_key": key,
        "title": title,
        "purpose": purpose,
        "evidence_expected": evidence,
        "levels": {"MEETS": meets, "NEEDS_WORK": needs_work},
        "required": True,
        "feedback_prompt": prompt,
        "blocking_rule": "REQUIRE_FEEDBACK",
    }


RUBRIC_V1 = {
    "version": 1,
    "dimensions": [
        _dimension(
            "problem_clarity", "问题清晰度", "确认问题、受影响对象和边界具体清楚。",
            "问题说明中的对象、场景和边界。", "问题具体且边界清楚", "问题仍宽泛或对象不清",
            "指出需要缩小或补充的对象与边界。",
        ),
        _dimension(
            "evidence_quality", "依据质量", "确认事实可核对且与假设分开。",
            "至少两条事实或观察。", "两条以上依据可核对", "依据不足或事实假设混淆",
            "指出需要补充或澄清的依据。",
        ),
        _dimension(
            "action_feasibility", "行动可执行性", "确认建议短、具体且责任明确。",
            "三步以内的行动、责任人和第一步。", "第一步与责任人明确", "行动不可执行或责任不清",
            "指出不可执行或责任不清之处。",
        ),
        _dimension(
            "validation_design", "验证设计", "确认两周内能够验证并安全停止或调整。",
            "验证指标和停止或调整条件。", "指标与护栏可观察", "无法验证或缺少护栏",
            "指出无法验证或缺少护栏之处。",
        ),
    ],
}


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
    op.get_bind().execute(
        sa.text(
            """
            UPDATE task_versions
            SET rubric = CAST(:rubric AS JSON), rubric_version = 1
            WHERE NOT ((rubric -> 'dimensions' -> 0)::jsonb ? 'dimension_key')
            """
        ),
        {"rubric": json.dumps(RUBRIC_V1, ensure_ascii=False)},
    )
    _create_immutability_trigger()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS task_versions_immutable ON task_versions")
    op.execute(
        """
        UPDATE task_versions
        SET rubric = json_build_object(
            'version', COALESCE((rubric ->> 'version')::integer, 1),
            'dimensions', (
                SELECT json_agg(
                    json_build_object(
                        'key', dimension ->> 'dimension_key',
                        'title', dimension ->> 'title',
                        'required', COALESCE((dimension ->> 'required')::boolean, true)
                    )
                )
                FROM json_array_elements(rubric -> 'dimensions') AS dimension
            )
        )
        WHERE (rubric -> 'dimensions' -> 0)::jsonb ? 'dimension_key'
        """
    )
    _create_immutability_trigger()
