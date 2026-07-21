import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.idempotency import find_replay, store_result
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    AuditEntry,
    Enrollment,
    EnrollmentStatus,
    Invite,
    InviteStatus,
    JoinContext,
    JoinContextStatus,
    NotificationDelivery,
    NotificationStatus,
    OutboxEvent,
    OutboxStatus,
    Review,
    ReviewStatus,
    Role,
    RoleAssignment,
    User,
    UserStatus,
    WorkerHeartbeat,
)
from journey_api.schemas import (
    AssignEnrollmentReviewerCommand,
    AuditEntryOut,
    AuditListOut,
    AuditListResponse,
    CancelEnrollmentCommand,
    EnrollmentMutationOut,
    EnrollmentMutationResponse,
    EnrollmentOpsListOut,
    EnrollmentOpsListResponse,
    EnrollmentOpsOut,
    RuntimeComponentOut,
    RuntimeMetricsOut,
    RuntimeStatusOut,
    RuntimeStatusResponse,
)


router = APIRouter(prefix="/api/v1/ops")
FILTER_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,120}$")
SAFE_AUDIT_KEYS = {
    "attachment_count",
    "audience",
    "content_source_count",
    "decision",
    "feedback_character_count",
    "reference_material_count",
    "role",
    "rubric_dimension_count",
    "rubric_version",
    "sensitivity",
    "stable_key",
    "status",
    "version",
}


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def ensure_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "状态已更新，请确认最新内容后重试。",
            details={"current_revision": actual},
        )


def scoped_enrollment(
    session: Session, actor: Actor, enrollment_id: uuid.UUID, *, for_update: bool
) -> Enrollment:
    query = select(Enrollment).where(
        Enrollment.id == enrollment_id,
        Enrollment.organization_id == actor.organization_id,
    )
    if for_update:
        query = query.with_for_update()
    enrollment = session.scalar(query)
    if enrollment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的 Enrollment。")
    return enrollment


def open_review_for_enrollment(
    session: Session, enrollment: Enrollment, *, for_update: bool
) -> Review | None:
    query = (
        select(Review)
        .join(Assignment, Assignment.id == Review.assignment_id)
        .where(
            Assignment.enrollment_id == enrollment.id,
            Review.organization_id == enrollment.organization_id,
            Review.status.in_([ReviewStatus.ASSIGNED, ReviewStatus.IN_REVIEW]),
        )
        .order_by(Review.assigned_at.desc(), Review.id)
    )
    if for_update:
        query = query.with_for_update()
    reviews = session.scalars(query).all()
    if len(reviews) > 1:
        raise ApiError(409, "VERSION_CONFLICT", "Enrollment 存在多个开放评审，需要先隔离处理。")
    return reviews[0] if reviews else None


def reviewer_in_scope(session: Session, actor: Actor, reviewer_id: uuid.UUID) -> User:
    reviewer = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == reviewer_id,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.REVIEWER,
        )
    )
    if reviewer is None:
        raise ApiError(422, "VALIDATION_FAILED", "新主管必须是同组织的有效 Reviewer。")
    return reviewer


def add_ops_facts(
    session: Session,
    *,
    request: Request,
    actor: Actor,
    action: str,
    event_type: str,
    resource_id: uuid.UUID,
    details: dict[str, object],
) -> None:
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action=action,
            resource_type="enrollment",
            resource_id=resource_id,
            result="SUCCESS",
            request_id=request.state.request_id,
            details=details,
        )
    )
    session.add(
        OutboxEvent(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            owner_id=actor.id,
            actor_id=actor.id,
            request_id=request.state.request_id,
            payload_version=1,
            event_type=event_type,
            aggregate_type="enrollment",
            aggregate_id=resource_id,
            payload={"enrollment_id": str(resource_id)},
            status=OutboxStatus.PENDING,
        )
    )


@router.get("/enrollments", response_model=EnrollmentOpsListResponse)
def list_enrollments(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    enrollments = session.scalars(
        select(Enrollment)
        .where(Enrollment.organization_id == actor.organization_id)
        .order_by(Enrollment.status, Enrollment.id)
        .limit(100)
    ).all()
    items: list[EnrollmentOpsOut] = []
    for enrollment in enrollments:
        learner = session.get(User, enrollment.learner_id)
        reviewer = session.get(User, enrollment.reviewer_id)
        assignments = session.scalars(
            select(Assignment)
            .where(
                Assignment.enrollment_id == enrollment.id,
                Assignment.organization_id == actor.organization_id,
            )
            .order_by(Assignment.position)
        ).all()
        open_review = open_review_for_enrollment(session, enrollment, for_update=False)
        allowed: list[str] = []
        if enrollment.status in {EnrollmentStatus.PENDING_IDENTITY, EnrollmentStatus.ACTIVE}:
            if open_review is None:
                allowed = ["assign_reviewer", "cancel_enrollment"]
        items.append(
            EnrollmentOpsOut(
                id=enrollment.id,
                learner_id=enrollment.learner_id,
                learner_display_name=learner.display_name if learner else "已停用身份",
                reviewer_id=enrollment.reviewer_id,
                reviewer_display_name=reviewer.display_name if reviewer else "已停用主管",
                status=enrollment.status.value,
                revision=enrollment.revision,
                assignment_statuses=[item.status.value for item in assignments],
                open_review_status=open_review.status.value if open_review else None,
                allowed_commands=allowed,
            )
        )
    return envelope(request, EnrollmentOpsListOut(items=items))


@router.put(
    "/enrollments/{enrollment_id}/reviewer",
    response_model=EnrollmentMutationResponse,
)
def assign_reviewer(
    enrollment_id: uuid.UUID,
    command: AssignEnrollmentReviewerCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "enrollment_id": str(enrollment_id)}
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="enrollment.assign_reviewer",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, EnrollmentMutationOut(**replay))
    enrollment = scoped_enrollment(session, actor, enrollment_id, for_update=True)
    ensure_revision(enrollment.revision, command.expected_revision)
    if enrollment.status not in {EnrollmentStatus.PENDING_IDENTITY, EnrollmentStatus.ACTIVE}:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前 Enrollment 不能更换主管。")
    if enrollment.reviewer_id == command.reviewer_id:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "新主管必须与当前主管不同。")
    reviewer_in_scope(session, actor, command.reviewer_id)
    open_review = open_review_for_enrollment(session, enrollment, for_update=True)
    if open_review is not None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已生成评审记录，不能更换主管或改写评审历史。")
    previous_reviewer_id = enrollment.reviewer_id
    enrollment.reviewer_id = command.reviewer_id
    enrollment.revision += 1
    result = {
        "resource_id": str(enrollment.id),
        "status": enrollment.status.value,
        "revision": enrollment.revision,
        "reviewer_id": str(enrollment.reviewer_id),
    }
    store_result(
        session,
        actor_id=actor.id,
        command="enrollment.assign_reviewer",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_ops_facts(
        session,
        request=request,
        actor=actor,
        action="enrollment.reviewer_assigned",
        event_type="enrollment.reviewer_assigned.v1",
        resource_id=enrollment.id,
        details={
            "previous_reviewer_id": str(previous_reviewer_id),
            "reviewer_id": str(command.reviewer_id),
            "reason": command.reason,
            "review_replaced": False,
        },
    )
    session.commit()
    return envelope(request, EnrollmentMutationOut(**result))


@router.post(
    "/enrollments/{enrollment_id}/cancel",
    response_model=EnrollmentMutationResponse,
)
def cancel_enrollment(
    enrollment_id: uuid.UUID,
    command: CancelEnrollmentCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "enrollment_id": str(enrollment_id)}
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="enrollment.cancel",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, EnrollmentMutationOut(**replay))
    enrollment = scoped_enrollment(session, actor, enrollment_id, for_update=True)
    ensure_revision(enrollment.revision, command.expected_revision)
    if enrollment.status not in {EnrollmentStatus.PENDING_IDENTITY, EnrollmentStatus.ACTIVE}:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前 Enrollment 不能取消。")
    open_review = open_review_for_enrollment(session, enrollment, for_update=True)
    if open_review is not None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已生成评审记录，不能取消 Enrollment 或改写评审历史。")
    assignments = session.scalars(
        select(Assignment)
        .where(
            Assignment.enrollment_id == enrollment.id,
            Assignment.organization_id == actor.organization_id,
        )
        .with_for_update()
    ).all()
    for assignment in assignments:
        if assignment.status in {
            AssignmentStatus.AVAILABLE,
            AssignmentStatus.IN_PROGRESS,
            AssignmentStatus.SUBMITTED,
            AssignmentStatus.NEEDS_REVISION,
        }:
            assignment.status = AssignmentStatus.CANCELLED
            assignment.revision += 1
        elif assignment.status == AssignmentStatus.IN_REVIEW:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "存在进行中的评审，不能取消。")
    join_context = session.scalar(
        select(JoinContext).where(JoinContext.enrollment_id == enrollment.id).with_for_update()
    )
    if join_context is not None and join_context.status == JoinContextStatus.PENDING:
        join_context.status = JoinContextStatus.REVOKED
        invite = session.scalar(
            select(Invite).where(Invite.id == join_context.invite_id).with_for_update()
        )
        if invite is not None and invite.status == InviteStatus.ACTIVE:
            invite.status = InviteStatus.REVOKED
            invite.revoked_at = datetime.now(UTC)
            invite.revoke_reason = command.reason
            invite.revision += 1
    enrollment.status = EnrollmentStatus.CANCELLED
    enrollment.revision += 1
    result = {
        "resource_id": str(enrollment.id),
        "status": enrollment.status.value,
        "revision": enrollment.revision,
        "reviewer_id": str(enrollment.reviewer_id),
    }
    store_result(
        session,
        actor_id=actor.id,
        command="enrollment.cancel",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_ops_facts(
        session,
        request=request,
        actor=actor,
        action="enrollment.cancelled",
        event_type="enrollment.cancelled.v1",
        resource_id=enrollment.id,
        details={"reason": command.reason, "cancelled_assignment_count": len(assignments)},
    )
    session.commit()
    return envelope(request, EnrollmentMutationOut(**result))


def safe_audit_details(details: dict[str, object]) -> tuple[dict[str, str | int | bool], list[str]]:
    safe: dict[str, str | int | bool] = {}
    redacted: list[str] = []
    for key, value in sorted(details.items()):
        if key in SAFE_AUDIT_KEYS and isinstance(value, (str, int, bool)):
            safe[key] = value
        else:
            redacted.append(key)
    return safe, redacted


@router.get("/audit", response_model=AuditListResponse)
def list_audit(
    request: Request,
    action: str | None = Query(default=None, max_length=120),
    resource_type: str | None = Query(default=None, max_length=80),
    result: str | None = Query(default=None, max_length=32),
    resource_id: uuid.UUID | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    for value in (action, resource_type, result):
        if value is not None and not FILTER_PATTERN.fullmatch(value):
            raise ApiError(400, "INVALID_REQUEST", "审计筛选值无效。")
    now = datetime.now(UTC)
    after = occurred_after or (now - timedelta(days=7))
    before = occurred_before or now
    if after.tzinfo is None or before.tzinfo is None or after >= before:
        raise ApiError(400, "INVALID_REQUEST", "审计时间范围无效。")
    if before - after > timedelta(days=31):
        raise ApiError(400, "INVALID_REQUEST", "单次审计查询不能超过 31 天。")
    query = select(AuditEntry).where(
        AuditEntry.organization_id == actor.organization_id,
        AuditEntry.occurred_at >= after,
        AuditEntry.occurred_at < before,
    )
    if action is not None:
        query = query.where(AuditEntry.action == action)
    if resource_type is not None:
        query = query.where(AuditEntry.resource_type == resource_type)
    if result is not None:
        query = query.where(AuditEntry.result == result)
    if resource_id is not None:
        query = query.where(AuditEntry.resource_id == resource_id)
    rows = session.scalars(query.order_by(AuditEntry.occurred_at.desc(), AuditEntry.id).limit(limit)).all()
    items: list[AuditEntryOut] = []
    for row in rows:
        safe, redacted = safe_audit_details(row.details)
        items.append(
            AuditEntryOut(
                id=row.id,
                actor_id=row.actor_id,
                action=row.action,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                result=row.result,
                request_id=row.request_id,
                safe_details=safe,
                redacted_fields=redacted,
                occurred_at=row.occurred_at,
            )
        )
    return envelope(request, AuditListOut(items=items))


@router.get("/runtime-status", response_model=RuntimeStatusResponse)
def runtime_status(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    settings = get_settings()
    migration_revision = session.scalar(text("SELECT version_num FROM alembic_version")) or "unknown"
    heartbeat = session.get(WorkerHeartbeat, "notification-worker")
    now = datetime.now(UTC)
    stale = heartbeat is None or heartbeat.last_seen_at < now - timedelta(seconds=15)
    backlog = session.scalar(
        select(func.count(OutboxEvent.id)).where(
            OutboxEvent.status.in_([OutboxStatus.PENDING, OutboxStatus.PROCESSING, OutboxStatus.FAILED]),
            OutboxEvent.processed_at.is_(None),
        )
    ) or 0
    dead = session.scalar(
        select(func.count(NotificationDelivery.id)).where(
            NotificationDelivery.status == NotificationStatus.DEAD
        )
    ) or 0
    denied = session.scalar(
        select(func.count(AuditEntry.id)).where(
            AuditEntry.organization_id == actor.organization_id,
            AuditEntry.result == "DENIED",
            AuditEntry.occurred_at >= now - timedelta(hours=24),
        )
    ) or 0
    data = RuntimeStatusOut(
        environment=settings.app_env,
        release=settings.app_release,
        config_schema_version=settings.config_schema_version,
        migration_revision=str(migration_revision),
        api=RuntimeComponentOut(status="READY", release=settings.app_release),
        database=RuntimeComponentOut(status="READY"),
        worker=RuntimeComponentOut(
            status="STALE" if stale else heartbeat.status,
            release=heartbeat.release if heartbeat else None,
            last_seen_at=heartbeat.last_seen_at if heartbeat else None,
            stale=stale,
        ),
        observability_mode="LOCAL_STRUCTURED_STDOUT",
        metrics=RuntimeMetricsOut(
            outbox_backlog=backlog,
            notification_dead=dead,
            permission_denials_24h=denied,
        ),
    )
    return envelope(request, data)
