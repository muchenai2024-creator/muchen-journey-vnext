import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.domain import AssignmentActionState, assignment_action, resolve_current_action
from journey_api.errors import ApiError
from journey_api.idempotency import find_replay, store_result
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    AuditEntry,
    Enrollment,
    EnrollmentStatus,
    OutboxEvent,
    OutboxStatus,
    Role,
    RoleAssignment,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
    User,
    UserStatus,
)
from journey_api.schemas import (
    AssignmentOut,
    AssignmentResponse,
    CommandOut,
    CommandResponse,
    CreateTaskDefinitionCommand,
    CurrentActionOut,
    CurrentActionResponse,
    HealthOut,
    RevisionCommand,
    PublishTaskVersionCommand,
    TaskDefinitionListOut,
    TaskDefinitionListResponse,
    TaskDefinitionOut,
    TaskDefinitionResponse,
    TaskVersionOut,
    TaskVersionResponse,
    TaskVersionSummaryOut,
)
from journey_api.submission_service import assignment_workspace

router = APIRouter()
api = APIRouter(prefix="/api/v1")

def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def lock_learner_assignment(session: Session, actor: Actor, assignment_id: uuid.UUID) -> Assignment:
    assignment = session.scalar(
        select(Assignment)
        .join(Enrollment, Enrollment.id == Assignment.enrollment_id)
        .where(
            Assignment.id == assignment_id,
            Assignment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
        .with_for_update()
    )
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的任务。")
    return assignment


def ensure_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "状态已更新，请确认最新内容后重试。",
            details={"current_revision": actual},
        )


def add_event(session: Session, event_type: str, aggregate_type: str, aggregate_id: uuid.UUID) -> None:
    session.add(
        OutboxEvent(
            id=uuid.uuid4(),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload={"aggregate_id": str(aggregate_id)},
            status=OutboxStatus.PENDING,
        )
    )


def add_audit(
    session: Session,
    *,
    request: Request,
    actor: Actor,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    details: dict[str, object],
) -> None:
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result="SUCCESS",
            request_id=request.state.request_id,
            details=details,
        )
    )


def task_definition_out(
    session: Session, definition: TaskDefinition, *, replay: bool = False
) -> TaskDefinitionOut:
    versions = session.scalars(
        select(TaskVersion)
        .where(TaskVersion.task_definition_id == definition.id)
        .order_by(TaskVersion.version)
    ).all()
    return TaskDefinitionOut(
        id=definition.id,
        stable_key=definition.stable_key,
        status=definition.status.value,
        revision=definition.revision,
        content_owner_id=definition.created_by,
        versions=[
            TaskVersionSummaryOut(
                id=version.id,
                version=version.version,
                title=version.title,
                published_at=version.published_at,
            )
            for version in versions
        ],
        idempotency_replay=replay,
    )


def task_version_out(
    version: TaskVersion, stable_key: str, *, replay: bool = False
) -> TaskVersionOut:
    return TaskVersionOut(
        id=version.id,
        task_definition_id=version.task_definition_id,
        stable_key=stable_key,
        version=version.version,
        title=version.title,
        purpose=version.purpose,
        learner_outcome=version.learner_outcome,
        instructions=version.instructions,
        completion_criteria=version.completion_criteria,
        required_deliverables=version.required_deliverables,
        content_source_notes=version.content_source_notes,
        change_summary=version.change_summary,
        reviewer_calibration_note=version.reviewer_calibration_note,
        allowed_attachment_types=version.allowed_attachment_types,
        max_attachment_size_bytes=version.max_attachment_size_bytes,
        reference_materials=version.reference_materials,
        estimated_duration_minutes=version.estimated_duration_minutes,
        rubric=version.rubric,
        rubric_version=version.rubric_version,
        reviewer_role=version.reviewer_role,
        feedback_sla_business_days=version.feedback_sla_business_days,
        sensitivity=version.sensitivity,
        audience=version.audience,
        published_by=version.published_by,
        reviewed_by=version.reviewed_by,
        published_at=version.published_at,
        idempotency_replay=replay,
    )


@router.get("/health/live", response_model=HealthOut)
def live() -> HealthOut:
    return HealthOut(status="ok", release=get_settings().app_release)


@router.get("/health/ready", response_model=HealthOut)
def ready(session: Session = Depends(get_db)) -> HealthOut:
    session.execute(select(1))
    return HealthOut(status="ok", release=get_settings().app_release)


@api.post("/ops/task-definitions", response_model=TaskDefinitionResponse)
def create_task_definition(
    command: CreateTaskDefinitionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="task_definition.create",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        definition = session.get(TaskDefinition, uuid.UUID(str(replay["id"])))
        if definition is None or definition.organization_id != actor.organization_id:
            raise ApiError(409, "VERSION_CONFLICT", "幂等结果引用的任务定义已不可用。")
        return envelope(request, task_definition_out(session, definition, replay=True))
    existing = session.scalar(
        select(TaskDefinition).where(
            TaskDefinition.organization_id == actor.organization_id,
            TaskDefinition.stable_key == command.stable_key,
        )
    )
    if existing is not None:
        raise ApiError(409, "VERSION_CONFLICT", "同一组织内已存在这个稳定任务编号。")
    definition = TaskDefinition(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        stable_key=command.stable_key,
        status=TaskDefinitionStatus.DRAFT,
        revision=1,
        created_by=actor.id,
    )
    session.add(definition)
    result = {
        "id": str(definition.id),
        "stable_key": definition.stable_key,
        "status": definition.status.value,
        "revision": definition.revision,
    }
    store_result(
        session,
        actor_id=actor.id,
        command="task_definition.create",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_audit(
        session,
        request=request,
        actor=actor,
        action="task_definition.created",
        resource_type="task_definition",
        resource_id=definition.id,
        details={"stable_key": definition.stable_key},
    )
    session.commit()
    return envelope(request, task_definition_out(session, definition))


@api.get("/ops/task-definitions", response_model=TaskDefinitionListResponse)
def list_task_definitions(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    definitions = session.scalars(
        select(TaskDefinition)
        .where(TaskDefinition.organization_id == actor.organization_id)
        .order_by(TaskDefinition.stable_key)
    ).all()
    return envelope(
        request,
        TaskDefinitionListOut(
            items=[task_definition_out(session, definition) for definition in definitions]
        ),
    )


@api.post(
    "/ops/task-definitions/{task_definition_id}/publish",
    response_model=TaskVersionResponse,
)
def publish_task_version(
    task_definition_id: uuid.UUID,
    command: PublishTaskVersionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {
        **command.model_dump(mode="json"),
        "task_definition_id": str(task_definition_id),
    }
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="task_version.publish",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        version = session.get(TaskVersion, uuid.UUID(str(replay["id"])))
        definition = session.get(TaskDefinition, task_definition_id)
        if (
            version is None
            or definition is None
            or version.organization_id != actor.organization_id
            or definition.organization_id != actor.organization_id
        ):
            raise ApiError(409, "VERSION_CONFLICT", "幂等结果引用的任务版本已不可用。")
        return envelope(request, task_version_out(version, definition.stable_key, replay=True))

    definition = session.scalar(
        select(TaskDefinition)
        .where(
            TaskDefinition.id == task_definition_id,
            TaskDefinition.organization_id == actor.organization_id,
            TaskDefinition.created_by == actor.id,
        )
        .with_for_update()
    )
    if definition is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可发布的任务定义。")
    ensure_revision(definition.revision, command.expected_revision)
    if definition.status == TaskDefinitionStatus.WITHDRAWN:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已撤销的任务定义不能发布新版本。")
    reviewer = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == command.reviewed_by,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.REVIEWER,
        )
    )
    if reviewer is None:
        raise ApiError(422, "VALIDATION_FAILED", "内容复核人必须是同组织的有效 Reviewer。")
    next_version = (
        session.scalar(
            select(func.max(TaskVersion.version)).where(
                TaskVersion.task_definition_id == definition.id
            )
        )
        or 0
    ) + 1
    version = TaskVersion(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        task_definition_id=definition.id,
        version=next_version,
        title=command.title.strip(),
        purpose=command.purpose.strip(),
        learner_outcome=command.learner_outcome.strip(),
        instructions=command.instructions,
        completion_criteria=command.completion_criteria,
        required_deliverables=command.required_deliverables,
        content_source_notes=command.content_source_notes,
        change_summary=command.change_summary.strip(),
        reviewer_calibration_note=command.reviewer_calibration_note.strip(),
        allowed_attachment_types=command.allowed_attachment_types,
        max_attachment_size_bytes=command.max_attachment_size_bytes,
        reference_materials=command.reference_materials,
        estimated_duration_minutes=command.estimated_duration_minutes,
        rubric=command.rubric.model_dump(mode="json"),
        rubric_version=command.rubric.version,
        reviewer_role=command.reviewer_role,
        feedback_sla_business_days=command.feedback_sla_business_days,
        sensitivity=command.sensitivity,
        audience=command.audience,
        published_by=actor.id,
        reviewed_by=command.reviewed_by,
    )
    session.add(version)
    session.flush()
    definition.status = TaskDefinitionStatus.PUBLISHED
    definition.revision += 1
    result = {"id": str(version.id), "task_definition_id": str(definition.id)}
    store_result(
        session,
        actor_id=actor.id,
        command="task_version.publish",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_event(session, "task_version.published.v1", "task_definition", definition.id)
    add_audit(
        session,
        request=request,
        actor=actor,
        action="task_version.published",
        resource_type="task_version",
        resource_id=version.id,
        details={
            "stable_key": definition.stable_key,
            "version": next_version,
            "drafted_by": str(definition.created_by),
            "reviewed_by": str(command.reviewed_by),
            "rubric_version": command.rubric.version,
            "sensitivity": command.sensitivity,
            "audience": command.audience,
            "reference_material_count": len(command.reference_materials),
            "content_source_count": len(command.content_source_notes),
            "change_summary": command.change_summary.strip(),
            "reviewer_calibration_note": command.reviewer_calibration_note.strip(),
        },
    )
    session.commit()
    return envelope(request, task_version_out(version, definition.stable_key))


@api.get("/me/current-action", response_model=CurrentActionResponse)
def current_action(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    enrollment = session.scalar(
        select(Enrollment)
        .where(
            Enrollment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
        )
        .order_by(
            case(
                (Enrollment.status == EnrollmentStatus.ACTIVE, 0),
                (Enrollment.status == EnrollmentStatus.PENDING_IDENTITY, 1),
                (Enrollment.status == EnrollmentStatus.COMPLETED, 2),
                else_=3,
            ),
            Enrollment.revision.desc(),
        )
    )
    assignment_rows: list[tuple[Assignment, TaskVersion]] = []
    reviewer: User | None = None
    if enrollment is not None:
        assignment_rows = list(
            session.execute(
                select(Assignment, TaskVersion)
                .join(TaskVersion, TaskVersion.id == Assignment.task_version_id)
                .where(
                    Assignment.enrollment_id == enrollment.id,
                    Assignment.organization_id == actor.organization_id,
                    TaskVersion.organization_id == actor.organization_id,
                )
                .order_by(Assignment.position, Assignment.id)
            ).all()
        )
        reviewer = session.scalar(
            select(User).where(
                User.id == enrollment.reviewer_id,
                User.organization_id == actor.organization_id,
            )
        )
    action = resolve_current_action(
        fallback_resource_id=enrollment.id if enrollment is not None else actor.id,
        fallback_revision=enrollment.revision if enrollment is not None else 1,
        enrollment_status=enrollment.status if enrollment is not None else None,
        assignments=tuple(
            AssignmentActionState(
                id=assignment.id,
                status=assignment.status,
                revision=assignment.revision,
                position=assignment.position,
            )
            for assignment, _ in assignment_rows
        ),
    )
    selected_task = next(
        (task for assignment, task in assignment_rows if assignment.id == action.resource_id),
        None,
    )
    data = CurrentActionOut(
        action_type=action.action_type,
        stage=action.stage,
        resource_id=action.resource_id,
        title=action.title,
        reason=action.reason,
        allowed_commands=list(action.allowed_commands),
        revision=action.revision,
        responsible_party=reviewer.display_name if reviewer is not None else "运营支持",
        feedback_expectation=(
            f"{selected_task.feedback_sla_business_days} 个工作日内"
            if selected_task is not None
            else "按当前加入状态处理"
        ),
    )
    return envelope(request, data)


@api.get("/me/assignments/{assignment_id}", response_model=AssignmentResponse)
def assignment_detail(
    assignment_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    row = session.execute(
        select(Assignment, TaskVersion, TaskDefinition)
        .join(Enrollment, Enrollment.id == Assignment.enrollment_id)
        .join(TaskVersion, TaskVersion.id == Assignment.task_version_id)
        .join(TaskDefinition, TaskDefinition.id == Assignment.task_definition_id)
        .where(
            Assignment.id == assignment_id,
            Assignment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
            TaskVersion.organization_id == actor.organization_id,
            TaskDefinition.organization_id == actor.organization_id,
        )
    ).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的任务。")
    assignment, task, definition = row
    commands = () if assignment.status == AssignmentStatus.CANCELLED else assignment_action(assignment.status)[4]
    submission, draft, available_attachments, latest_feedback = assignment_workspace(
        session, actor, assignment.id
    )
    data = AssignmentOut(
        id=assignment.id,
        status=assignment.status.value,
        revision=assignment.revision,
        allowed_commands=list(commands),
        stable_task_key=definition.stable_key,
        task_version=task.version,
        task_title=task.title,
        task_purpose=task.purpose,
        learner_outcome=task.learner_outcome,
        instructions=task.instructions,
        completion_criteria=task.completion_criteria,
        required_deliverables=task.required_deliverables,
        allowed_attachment_types=task.allowed_attachment_types,
        max_attachment_size_bytes=task.max_attachment_size_bytes,
        reference_materials=task.reference_materials,
        estimated_duration_minutes=task.estimated_duration_minutes,
        feedback_sla_business_days=task.feedback_sla_business_days,
        rubric=task.rubric,
        submission=submission,
        draft=draft,
        available_attachments=available_attachments,
        latest_revision_feedback=latest_feedback,
    )
    return envelope(request, data)


@api.post("/me/assignments/{assignment_id}/start", response_model=CommandResponse)
def start_assignment(
    assignment_id: uuid.UUID,
    command: RevisionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    payload = command.model_dump(mode="json")
    replay = find_replay(
        session, actor_id=actor.id, command="assignment.start", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return envelope(request, CommandOut(**replay))
    assignment = lock_learner_assignment(session, actor, assignment_id)
    replay = find_replay(
        session, actor_id=actor.id, command="assignment.start", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return envelope(request, CommandOut(**replay))
    ensure_revision(assignment.revision, command.expected_revision)
    if assignment.status != AssignmentStatus.AVAILABLE:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前任务不能执行开始操作。")
    assignment.status = AssignmentStatus.IN_PROGRESS
    assignment.revision += 1
    result = {"resource_id": str(assignment.id), "status": assignment.status.value, "revision": assignment.revision}
    store_result(
        session,
        actor_id=actor.id,
        command="assignment.start",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_event(session, "assignment.started.v1", "assignment", assignment.id)
    session.commit()
    return envelope(request, CommandOut(**result))


router.include_router(api)
