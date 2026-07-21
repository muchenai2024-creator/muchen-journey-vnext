import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

import test_reviewer_workbench as wp04
from journey_api.db import SessionLocal
from journey_api.main import app
from journey_api.models import (
    Handoff,
    LocalNotificationReceipt,
    NotificationAttempt,
    NotificationAttemptStatus,
    NotificationChannel,
    NotificationDelivery,
    NotificationStatus,
    Outcome,
    OutboxEvent,
    OutboxStatus,
)


def approve(label: str) -> dict[str, object]:
    flow = wp04.create_submission(f"wp05-{label}")
    reviewer = wp04.client_for(f"wp05-reviewer-{label}")
    started = wp04.assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={
                **wp04.REVIEWER_HEADERS,
                "Idempotency-Key": f"wp05-start-{uuid.uuid4()}",
            },
            json={"expected_revision": 1},
        )
    )
    final_key = f"wp05-final-{uuid.uuid4()}"
    payload = wp04.finalize_payload(
        started["review_revision"],
        decision="APPROVE",
        overall_feedback=f"{label}：四个维度均达到批准锚点，形成最终人工评价。",
    )
    finalized = wp04.assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/finalize",
            headers={**wp04.REVIEWER_HEADERS, "Idempotency-Key": final_key},
            json=payload,
        )
    )
    assert finalized["decision"] == "PASS"
    flow.update(
        {
            "reviewer": reviewer,
            "final_key": final_key,
            "final_payload": payload,
            "evaluation_id": uuid.UUID(finalized["evaluation_id"]),
        }
    )
    return flow


def notification_state(evaluation_id: uuid.UUID):
    with SessionLocal() as session:
        outcome = session.scalar(
            select(Outcome).where(Outcome.source_evaluation_id == evaluation_id)
        )
        assert outcome is not None
        handoff = session.scalar(select(Handoff).where(Handoff.outcome_id == outcome.id))
        assert handoff is not None
        delivery = session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.outcome_id == outcome.id
            )
        )
        assert delivery is not None
        event = session.get(OutboxEvent, delivery.event_id)
        assert event is not None
        return outcome, handoff, delivery, event


def run_worker(
    event_id: uuid.UUID,
    *,
    behavior: str,
    max_attempts: int = 3,
    crash_after_delivery: bool = False,
    lease_seconds: int = 30,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "APP_ENV": "test",
        "NOTIFICATION_ADAPTER": "LOCAL_TEST",
        "LOCAL_NOTIFICATION_BEHAVIOR": behavior,
        "NOTIFICATION_MAX_ATTEMPTS": str(max_attempts),
        "NOTIFICATION_RETRY_BASE_SECONDS": "0",
        "OUTBOX_LEASE_SECONDS": str(lease_seconds),
        "WORKER_TEST_CRASH_AFTER_DELIVERY": (
            "true" if crash_after_delivery else "false"
        ),
    }
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "journey_worker.main",
            "--once",
            "--event-id",
            str(event_id),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_result_handoff_timeline_scope_immutability_and_get_purity():
    first = approve("result-scope-first")
    outcome, handoff, delivery, event = notification_state(first["evaluation_id"])

    replay = wp04.assert_ok(
        first["reviewer"].post(
            f"/api/v1/reviews/{first['review_id']}/finalize",
            headers={
                **wp04.REVIEWER_HEADERS,
                "Idempotency-Key": first["final_key"],
            },
            json=first["final_payload"],
        )
    )
    assert replay["idempotency_replay"] is True

    with SessionLocal() as session:
        bundle_counts_before = (
            session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.source_evaluation_id == first["evaluation_id"]
                )
            ),
            session.scalar(
                select(func.count(Handoff.id)).where(Handoff.outcome_id == outcome.id)
            ),
            session.scalar(
                select(func.count(OutboxEvent.id)).where(
                    OutboxEvent.aggregate_id.in_([outcome.id, handoff.id])
                )
            ),
            session.scalar(
                select(func.count(NotificationDelivery.id)).where(
                    NotificationDelivery.outcome_id == outcome.id
                )
            ),
        )
    assert bundle_counts_before == (1, 1, 3, 1)
    assert event.organization_id == outcome.organization_id
    assert event.owner_id == outcome.learner_id
    assert event.aggregate_id == outcome.id
    assert event.payload == {
        "outcome_id": str(outcome.id),
        "template_version": "outcome-ready.v1",
    }
    mutating_notification_paths = [
        (path, method)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if "notification" in path and method.lower() not in {"get", "parameters"}
    ]
    assert mutating_notification_paths == []

    result_first = wp04.assert_ok(first["learner"].get("/api/v1/me/result"))
    result_second = wp04.assert_ok(first["learner"].get("/api/v1/me/result"))
    timeline_first = wp04.assert_ok(
        first["learner"].get("/api/v1/me/timeline?limit=100")
    )
    timeline_second = wp04.assert_ok(
        first["learner"].get("/api/v1/me/timeline?limit=100")
    )
    assert result_first == result_second
    assert timeline_first == timeline_second
    assert result_first["decision"] == "PASS"
    assert result_first["evaluation"]["decision"] == "PASS"
    assert len(result_first["evaluation"]["rubric_feedback"]) == 4
    assert result_first["handoff"]["next_step_code"] == "CONFIRM_HANDOFF"
    assert result_first["notification"]["status"] == "PENDING"
    assert result_first["notification"]["delivery_scope"] == "LOCAL_TEST_ONLY"
    assert result_first["notification"]["external_delivery_confirmed"] is False
    assert result_first["ai_summary"]["status"] == "NOT_ENABLED"
    event_types = {item["event_type"] for item in timeline_first["items"]}
    assert {
        "SUBMISSION_VERSION_CREATED",
        "REVIEW_ASSIGNED",
        "REVIEW_STARTED",
        "EVALUATION_FINALIZED",
        "OUTCOME_CREATED",
        "HANDOFF_READY",
        "NOTIFICATION_REQUESTED",
    }.issubset(event_types)

    second = approve("result-scope-second")
    second_outcome, second_handoff, second_delivery, second_event = notification_state(
        second["evaluation_id"]
    )
    scoped_json = json.dumps(
        wp04.assert_ok(first["learner"].get("/api/v1/me/timeline?limit=100")),
        ensure_ascii=False,
    )
    for foreign_id in (
        second_outcome.id,
        second_handoff.id,
        second_delivery.id,
        second_event.id,
        second["review_id"],
        second["evaluation_id"],
    ):
        assert str(foreign_id) not in scoped_json

    now = datetime.now(UTC)
    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as session:
            mismatched_event = OutboxEvent(
                id=uuid.uuid4(),
                organization_id=outcome.organization_id,
                owner_id=outcome.learner_id,
                actor_id=handoff.owner_user_id,
                request_id="req_wp05_scope_negative",
                payload_version=1,
                event_type="notification.requested.v1",
                aggregate_type="outcome",
                aggregate_id=outcome.id,
                payload={"outcome_id": str(outcome.id)},
                status=OutboxStatus.PENDING,
                attempt_count=0,
                next_attempt_at=now,
                dedupe_key=f"scope-negative:{uuid.uuid4()}",
                occurred_at=now,
            )
            session.add(mismatched_event)
            session.flush()
            session.add(
                NotificationDelivery(
                    id=uuid.uuid4(),
                    organization_id=second_outcome.organization_id,
                    event_id=mismatched_event.id,
                    outcome_id=second_outcome.id,
                    recipient_user_id=second_outcome.learner_id,
                    channel=NotificationChannel.LOCAL_TEST,
                    template_version="outcome-ready.v1",
                    status=NotificationStatus.PENDING,
                    attempt_count=0,
                    next_attempt_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
    assert (
        wp04.client_for("wp05-reviewer-timeline").get(
            "/api/v1/me/timeline", headers=wp04.REVIEWER_HEADERS
        ).status_code
        == 403
    )
    assert first["learner"].get("/api/v1/me/timeline?cursor=not-a-cursor").status_code == 400
    first_page = wp04.assert_ok(
        first["learner"].get("/api/v1/me/timeline?limit=2")
    )
    assert len(first_page["items"]) == 2
    assert first_page["next_cursor"] is not None
    second_page = wp04.assert_ok(
        first["learner"].get(
            "/api/v1/me/timeline",
            params={"limit": 100, "cursor": first_page["next_cursor"]},
        )
    )
    assert not (
        {item["item_id"] for item in first_page["items"]}
        & {item["item_id"] for item in second_page["items"]}
    )

    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.source_evaluation_id == first["evaluation_id"]
                )
            ),
            session.scalar(
                select(func.count(Handoff.id)).where(Handoff.outcome_id == outcome.id)
            ),
            session.scalar(
                select(func.count(OutboxEvent.id)).where(
                    OutboxEvent.aggregate_id.in_([outcome.id, handoff.id])
                )
            ),
            session.scalar(
                select(func.count(NotificationDelivery.id)).where(
                    NotificationDelivery.outcome_id == outcome.id
                )
            ),
        ) == bundle_counts_before

    for model, row_id, values in (
        (Outcome, outcome.id, {"summary": "不得覆盖旧结果"}),
        (Handoff, handoff.id, {"next_step_title": "不得覆盖唯一下一步"}),
    ):
        with pytest.raises(DBAPIError):
            with SessionLocal.begin() as session:
                session.execute(update(model).where(model.id == row_id).values(**values))


def test_real_worker_retry_failure_and_dead_letter_do_not_change_result():
    concurrent_flow = approve("worker-concurrent")
    _, _, concurrent_delivery, concurrent_event = notification_state(
        concurrent_flow["evaluation_id"]
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent_runs = list(
            executor.map(
                lambda _index: run_worker(concurrent_event.id, behavior="success"),
                range(2),
            )
        )
    assert all(run.returncode == 0 for run in concurrent_runs)
    assert sum("processed=1" in run.stderr for run in concurrent_runs) == 1
    assert all(str(concurrent_event.id) not in run.stderr for run in concurrent_runs)
    _, _, concurrent_delivery, concurrent_event = notification_state(
        concurrent_flow["evaluation_id"]
    )
    assert concurrent_event.status == OutboxStatus.SENT
    assert concurrent_event.attempt_count == 1
    with SessionLocal() as session:
        assert session.scalar(
            select(func.count(LocalNotificationReceipt.id)).where(
                LocalNotificationReceipt.delivery_id == concurrent_delivery.id
            )
        ) == 1
        assert session.scalar(
            select(func.count(NotificationAttempt.id)).where(
                NotificationAttempt.delivery_id == concurrent_delivery.id
            )
        ) == 1

    retry_flow = approve("worker-retry")
    retry_outcome, _, retry_delivery, retry_event = notification_state(
        retry_flow["evaluation_id"]
    )
    result_before = wp04.assert_ok(retry_flow["learner"].get("/api/v1/me/result"))

    failed = run_worker(retry_event.id, behavior="fail_once")
    assert failed.returncode == 0, failed.stderr
    _, _, retry_delivery, retry_event = notification_state(retry_flow["evaluation_id"])
    assert retry_event.status == OutboxStatus.FAILED
    assert retry_event.attempt_count == 1
    assert retry_event.next_attempt_at is not None
    assert retry_delivery.status == NotificationStatus.RETRY_WAIT
    assert retry_delivery.last_error_code == "LOCAL_ADAPTER_UNAVAILABLE"

    succeeded = run_worker(retry_event.id, behavior="success")
    assert succeeded.returncode == 0, succeeded.stderr
    _, _, retry_delivery, retry_event = notification_state(retry_flow["evaluation_id"])
    assert retry_event.status == OutboxStatus.SENT
    assert retry_event.attempt_count == 2
    assert retry_delivery.status == NotificationStatus.DELIVERED
    assert retry_delivery.attempt_count == 2
    assert retry_delivery.delivered_at is not None
    with SessionLocal() as session:
        statuses = session.scalars(
            select(NotificationAttempt.status)
            .where(NotificationAttempt.delivery_id == retry_delivery.id)
            .order_by(NotificationAttempt.attempt_number)
        ).all()
        assert statuses == [
            NotificationAttemptStatus.FAILED_RETRYABLE,
            NotificationAttemptStatus.DELIVERED,
        ]
    result_after = wp04.assert_ok(retry_flow["learner"].get("/api/v1/me/result"))
    assert result_after["outcome_id"] == str(retry_outcome.id)
    assert result_after["evaluation"] == result_before["evaluation"]
    assert result_after["handoff"] == result_before["handoff"]
    assert result_after["notification"]["status"] == "DELIVERED"
    assert result_after["notification"]["external_delivery_confirmed"] is False

    dead_flow = approve("worker-dead")
    dead_outcome, _, _, dead_event = notification_state(dead_flow["evaluation_id"])
    for _ in range(2):
        process = run_worker(dead_event.id, behavior="always_fail", max_attempts=2)
        assert process.returncode == 0, process.stderr
        _, _, dead_delivery, dead_event = notification_state(dead_flow["evaluation_id"])
    assert dead_event.status == OutboxStatus.FAILED
    assert dead_event.attempt_count == 2
    assert dead_event.next_attempt_at is None
    assert dead_delivery.status == NotificationStatus.DEAD
    assert dead_delivery.last_error_code == "LOCAL_ADAPTER_UNAVAILABLE"
    dead_result = wp04.assert_ok(dead_flow["learner"].get("/api/v1/me/result"))
    assert dead_result["outcome_id"] == str(dead_outcome.id)
    assert dead_result["decision"] == "PASS"
    assert dead_result["notification"]["status"] == "DEAD"


def test_real_worker_recovers_after_adapter_commit_without_duplicate_delivery():
    flow = approve("worker-crash-dedupe")
    _, _, delivery, event = notification_state(flow["evaluation_id"])

    crashed = run_worker(event.id, behavior="success", crash_after_delivery=True)
    assert crashed.returncode != 0
    assert str(event.id) not in crashed.stdout + crashed.stderr
    _, _, delivery, event = notification_state(flow["evaluation_id"])
    assert event.status == OutboxStatus.PROCESSING
    assert delivery.status == NotificationStatus.SENDING
    with SessionLocal() as session:
        assert session.scalar(
            select(func.count(LocalNotificationReceipt.id)).where(
                LocalNotificationReceipt.delivery_id == delivery.id
            )
        ) == 1

    with SessionLocal.begin() as session:
        session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event.id)
            .values(locked_at=datetime.now(UTC) - timedelta(seconds=31))
        )

    recovered = run_worker(event.id, behavior="success")
    assert recovered.returncode == 0, recovered.stderr
    assert "deduplicated=True" in recovered.stderr
    _, _, delivery, event = notification_state(flow["evaluation_id"])
    assert event.status == OutboxStatus.SENT
    assert event.attempt_count == 2
    assert delivery.status == NotificationStatus.DELIVERED
    with SessionLocal() as session:
        assert session.scalar(
            select(func.count(LocalNotificationReceipt.id)).where(
                LocalNotificationReceipt.delivery_id == delivery.id
            )
        ) == 1
        attempts = session.execute(
            select(NotificationAttempt.attempt_number, NotificationAttempt.status)
            .where(NotificationAttempt.delivery_id == delivery.id)
            .order_by(NotificationAttempt.attempt_number)
        ).all()
        assert attempts == [
            (1, NotificationAttemptStatus.LEASE_EXPIRED),
            (2, NotificationAttemptStatus.DELIVERED),
        ]

    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as session:
            session.execute(
                update(NotificationAttempt)
                .where(NotificationAttempt.delivery_id == delivery.id)
                .values(error_code="CANNOT_REWRITE_HISTORY")
            )

    nonlocal_env = {
        **os.environ,
        "APP_ENV": "production",
        "ALLOW_FIXTURE_IDENTITY": "false",
        "SESSION_SECRET": "wp05-production-test-session-secret-00000001",
        "INVITE_SECRET": "wp05-production-test-invite-secret-000000002",
        "IMPORT_SIGNING_KEY": "wp06-production-test-import-signing-key-000003",
        "NOTIFICATION_ADAPTER": "LOCAL_TEST",
    }
    blocked = subprocess.run(
        [sys.executable, "-m", "journey_worker.main", "--once"],
        env=nonlocal_env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert blocked.returncode != 0
    assert "disabled outside local/test" in blocked.stderr
