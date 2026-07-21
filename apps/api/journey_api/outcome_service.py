from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from journey_api.models import (
    Assignment,
    Enrollment,
    Evaluation,
    Handoff,
    HandoffStatus,
    NotificationChannel,
    NotificationDelivery,
    NotificationStatus,
    Outcome,
    OutboxEvent,
    OutboxStatus,
)


def add_scoped_outbox_event(
    session: Session,
    *,
    event_id: uuid.UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID,
    actor_id: uuid.UUID,
    request_id: str,
    dedupe_key: str,
    payload: dict[str, object],
    occurred_at: datetime,
) -> OutboxEvent:
    event = OutboxEvent(
        id=event_id,
        organization_id=organization_id,
        owner_id=owner_id,
        actor_id=actor_id,
        request_id=request_id,
        payload_version=1,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        status=OutboxStatus.PENDING,
        attempt_count=0,
        next_attempt_at=occurred_at,
        dedupe_key=dedupe_key,
        occurred_at=occurred_at,
    )
    session.add(event)
    return event


def create_pass_outcome_bundle(
    session: Session,
    *,
    enrollment: Enrollment,
    assignment: Assignment,
    evaluation: Evaluation,
    reviewer_id: uuid.UUID,
    request_id: str,
) -> tuple[Outcome, Handoff, NotificationDelivery]:
    """Create the result, one next step, and its notification request atomically."""

    now = datetime.now(UTC)
    outcome = Outcome(
        id=uuid.uuid4(),
        organization_id=enrollment.organization_id,
        learner_id=enrollment.learner_id,
        assignment_id=assignment.id,
        enrollment_id=enrollment.id,
        source_evaluation_id=evaluation.id,
        status="HANDOFF_READY",
        summary="任务已通过并形成最终人工评价，探索营交接已准备。",
        created_at=now,
    )
    handoff = Handoff(
        id=uuid.uuid4(),
        organization_id=enrollment.organization_id,
        enrollment_id=enrollment.id,
        outcome_id=outcome.id,
        source_evaluation_id=evaluation.id,
        owner_user_id=reviewer_id,
        status=HandoffStatus.READY,
        title="探索营交接已准备",
        next_step_code="CONFIRM_HANDOFF",
        next_step_title="与交接责任人确认下一步",
        instructions="查看主管的结构化反馈，并与交接责任人确认后续安排。",
        created_at=now,
    )
    # Flush in dependency order while retaining one surrounding transaction.  The
    # fixed-scope composite foreign keys deliberately do not rely on nullable or
    # single-column shortcuts, so making the order explicit also keeps failures
    # local to this atomic bundle.
    session.add(outcome)
    session.flush()
    session.add(handoff)
    session.flush()

    add_scoped_outbox_event(
        session,
        event_id=uuid.uuid4(),
        event_type="outcome.created.v1",
        aggregate_type="outcome",
        aggregate_id=outcome.id,
        organization_id=enrollment.organization_id,
        owner_id=enrollment.learner_id,
        actor_id=reviewer_id,
        request_id=request_id,
        dedupe_key=f"outcome.created:{outcome.id}",
        payload={"outcome_id": str(outcome.id)},
        occurred_at=now,
    )
    add_scoped_outbox_event(
        session,
        event_id=uuid.uuid4(),
        event_type="handoff.ready.v1",
        aggregate_type="handoff",
        aggregate_id=handoff.id,
        organization_id=enrollment.organization_id,
        owner_id=enrollment.learner_id,
        actor_id=reviewer_id,
        request_id=request_id,
        dedupe_key=f"handoff.ready:{handoff.id}",
        payload={"handoff_id": str(handoff.id), "outcome_id": str(outcome.id)},
        occurred_at=now,
    )

    event_id = uuid.uuid4()
    template_version = "outcome-ready.v1"
    dedupe_key = (
        f"notification:{outcome.id}:{enrollment.learner_id}:"
        f"{NotificationChannel.LOCAL_TEST.value}:{template_version}"
    )
    notification_event = add_scoped_outbox_event(
        session,
        event_id=event_id,
        event_type="notification.requested.v1",
        aggregate_type="outcome",
        aggregate_id=outcome.id,
        organization_id=enrollment.organization_id,
        owner_id=enrollment.learner_id,
        actor_id=reviewer_id,
        request_id=request_id,
        dedupe_key=dedupe_key,
        payload={
            "outcome_id": str(outcome.id),
            "template_version": template_version,
        },
        occurred_at=now,
    )
    session.flush()
    delivery = NotificationDelivery(
        id=uuid.uuid4(),
        organization_id=enrollment.organization_id,
        event_id=notification_event.id,
        outcome_id=outcome.id,
        recipient_user_id=enrollment.learner_id,
        channel=NotificationChannel.LOCAL_TEST,
        template_version=template_version,
        status=NotificationStatus.PENDING,
        attempt_count=0,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(delivery)
    return outcome, handoff, delivery
