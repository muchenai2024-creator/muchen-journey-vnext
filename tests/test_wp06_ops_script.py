import copy

import pytest

from scripts.wp06_ops import EXTERNAL_BLOCKERS, OpsError, alert_decisions, evaluate_release_gate


def evidence(status: str = "PASS") -> dict[str, object]:
    from scripts.wp06_ops import REQUIRED_RELEASE_CHECKS

    return {
        "schema_version": 1,
        "candidate": "test-candidate",
        "checks": {name: status for name in REQUIRED_RELEASE_CHECKS},
    }


def test_release_gate_is_fail_closed_for_missing_not_run_and_failed_checks():
    document = evidence()
    document["checks"]["real_human_uat"] = "NOT_RUN"  # type: ignore[index]
    decision = evaluate_release_gate(document)
    assert decision["decision"] == "NO_GO"
    assert decision["blockers"] == ["real_human_uat"]

    missing = evidence()
    del missing["checks"]["physical_acl_validation"]  # type: ignore[index]
    missing_decision = evaluate_release_gate(missing)
    assert "physical_acl_validation" in missing_decision["blockers"]

    failed = evidence()
    failed["checks"]["local_backup_isolated_restore"] = "FAIL"  # type: ignore[index]
    assert evaluate_release_gate(failed)["decision"] == "NO_GO"


def test_release_gate_requires_strict_known_schema_and_preserves_external_blockers():
    document = evidence("NOT_RUN")
    result = evaluate_release_gate(document)
    assert EXTERNAL_BLOCKERS.issubset(set(result["blockers"]))
    unknown = copy.deepcopy(document)
    unknown["checks"]["invented_approval"] = "PASS"  # type: ignore[index]
    with pytest.raises(OpsError):
        evaluate_release_gate(unknown)


def test_alert_policy_detects_worker_queue_and_revision_failures():
    assert alert_decisions(
        {
            "worker_stale": True,
            "outbox_backlog": 10,
            "notification_dead": 1,
            "api_release": "candidate",
            "worker_release": "previous",
            "migration_revision": "0009_notification_scope",
        }
    ) == [
        "WORKER_STALE",
        "OUTBOX_BACKLOG_HIGH",
        "NOTIFICATION_DEAD",
        "RELEASE_REVISION_MISMATCH",
        "MIGRATION_REVISION_MISMATCH",
    ]
