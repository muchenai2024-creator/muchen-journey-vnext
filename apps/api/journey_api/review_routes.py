from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.idempotency import find_replay, store_result
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Attachment,
    AttachmentScanStatus,
    AttachmentStatus,
    AuditEntry,
    Decision,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    OutboxEvent,
    OutboxStatus,
    Review,
    ReviewStatus,
    Role,
    Submission,
    SubmissionVersion,
    SubmissionVersionAttachment,
    TaskDefinition,
    TaskVersion,
    User,
)
from journey_api.outcome_service import create_pass_outcome_bundle
from journey_api.schemas import (
    EvaluationOut,
    FinalizeReviewCommand,
    ReviewAttachmentOut,
    ReviewDetailOut,
    ReviewDetailResponse,
    ReviewMaterialOut,
    ReviewMutationOut,
    ReviewMutationResponse,
    ReviewQueueItemOut,
    ReviewQueueOut,
    ReviewQueueResponse,
    RevisionCommand,
    RubricEvaluationOut,
)


router = APIRouter(prefix="/api/v1")


@dataclass(frozen=True)
class ReviewContext:
    review: Review
    assignment: Assignment
    submission: Submission
    version: SubmissionVersion
    enrollment: Enrollment
    learner: User
    definition: TaskDefinition
    task: TaskVersion
    evaluation: Evaluation | None


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def ensure_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "评审状态已更新，请确认最新内容后重试。",
            details={"current_revision": actual},
        )


def allowed_commands(status: ReviewStatus) -> list[str]:
    if status == ReviewStatus.ASSIGNED:
        return ["start"]
    if status == ReviewStatus.IN_REVIEW:
        return ["approve", "request_revision"]
    return []


def priority_reason(review: Review, version: SubmissionVersion) -> str:
    if review.status == ReviewStatus.IN_REVIEW:
        return "已开始评审，请优先完成"
    if version.version_no > 1:
        return "修订提交，优先复评"
    return "按等待时间排序"


def scoped_context_query(actor: Actor, review_id: uuid.UUID):
    return (
        select(
            Review,
            Assignment,
            Submission,
            SubmissionVersion,
            Enrollment,
            User,
            TaskDefinition,
            TaskVersion,
            Evaluation,
        )
        .join(Assignment, Assignment.id == Review.assignment_id)
        .join(Submission, Submission.id == Review.submission_id)
        .join(SubmissionVersion, SubmissionVersion.id == Review.submission_version_id)
        .join(Enrollment, Enrollment.id == Assignment.enrollment_id)
        .join(User, User.id == Enrollment.learner_id)
        .join(TaskDefinition, TaskDefinition.id == Assignment.task_definition_id)
        .join(TaskVersion, TaskVersion.id == Assignment.task_version_id)
        .outerjoin(Evaluation, Evaluation.review_id == Review.id)
        .where(
            Review.id == review_id,
            Review.organization_id == actor.organization_id,
            Review.reviewer_id == actor.id,
            Assignment.organization_id == actor.organization_id,
            Submission.organization_id == actor.organization_id,
            Enrollment.organization_id == actor.organization_id,
            User.organization_id == actor.organization_id,
            TaskDefinition.organization_id == actor.organization_id,
            TaskVersion.organization_id == actor.organization_id,
        )
    )


def get_scoped_context(
    session: Session, actor: Actor, review_id: uuid.UUID
) -> ReviewContext:
    row = session.execute(scoped_context_query(actor, review_id)).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的评审。")
    return ReviewContext(*row)


def lock_scoped_context(
    session: Session, actor: Actor, review_id: uuid.UUID
) -> ReviewContext:
    review = session.scalar(
        select(Review)
        .where(
            Review.id == review_id,
            Review.organization_id == actor.organization_id,
            Review.reviewer_id == actor.id,
        )
        .with_for_update()
    )
    if review is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的评审。")
    assignment = session.scalar(
        select(Assignment)
        .where(
            Assignment.id == review.assignment_id,
            Assignment.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if assignment is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "评审缺少固定任务引用。")
    return get_scoped_context(session, actor, review_id)


def review_materials(session: Session, context: ReviewContext) -> ReviewMaterialOut:
    rows = session.execute(
        select(SubmissionVersionAttachment, Attachment)
        .join(Attachment, Attachment.id == SubmissionVersionAttachment.attachment_id)
        .where(
            SubmissionVersionAttachment.submission_version_id == context.version.id,
            SubmissionVersionAttachment.submission_id == context.submission.id,
            SubmissionVersionAttachment.organization_id == context.review.organization_id,
            SubmissionVersionAttachment.assignment_id == context.assignment.id,
        )
        .order_by(SubmissionVersionAttachment.position)
    ).all()
    missing_items: list[str] = []
    if len(context.version.body.strip()) < 40:
        missing_items.append("固定提交正文不可用或不符合最小长度合同")
    attachments: list[ReviewAttachmentOut] = []
    for _link, attachment in rows:
        available = (
            attachment.status == AttachmentStatus.READY
            and attachment.scan_status == AttachmentScanStatus.LOCAL_CLEAN
        )
        if not available:
            missing_items.append(f"附件 {attachment.original_filename} 当前不可用")
        attachments.append(
            ReviewAttachmentOut(
                id=attachment.id,
                original_filename=attachment.original_filename,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                status=attachment.status.value,
                scan_status=attachment.scan_status.value,
                download_path=f"/api/v1/attachments/{attachment.id}/download",
            )
        )
    return ReviewMaterialOut(
        status="INCOMPLETE" if missing_items else "COMPLETE",
        missing_items=missing_items,
        required_deliverables=list(context.task.required_deliverables),
        attachments=attachments,
    )


def evaluation_out(evaluation: Evaluation) -> EvaluationOut:
    structured = evaluation.structured_feedback
    rubric_evaluations: list[RubricEvaluationOut]
    if evaluation.feedback_structure_version == 1 and isinstance(structured, list):
        rubric_evaluations = [RubricEvaluationOut(**item) for item in structured]
    else:
        rubric_evaluations = [
            RubricEvaluationOut(
                dimension_key=dimension_key,
                rating=rating,
                feedback=None,
            )
            for dimension_key, rating in evaluation.rubric_scores.items()
        ]
    return EvaluationOut(
        id=evaluation.id,
        decision=evaluation.decision.value,
        overall_decision=(
            "APPROVE" if evaluation.decision == Decision.PASS else "REQUEST_REVISION"
        ),
        overall_feedback=evaluation.feedback,
        rubric_evaluations=rubric_evaluations,
        feedback_structure_version=evaluation.feedback_structure_version,
        reviewer_id=evaluation.reviewer_id,
        review_revision=evaluation.review_revision,
        created_at=evaluation.created_at,
    )


def queue_item(
    session: Session, context: ReviewContext, *, materials: ReviewMaterialOut | None = None
) -> ReviewQueueItemOut:
    material_state = materials or review_materials(session, context)
    return ReviewQueueItemOut(
        id=context.review.id,
        assignment_id=context.assignment.id,
        submission_id=context.submission.id,
        submission_version_id=context.version.id,
        status=context.review.status.value,
        revision=context.review.revision,
        allowed_commands=allowed_commands(context.review.status),
        learner_name=context.learner.display_name,
        task_title=context.task.title,
        task_version=context.task.version,
        submission_version_no=context.version.version_no,
        assigned_at=context.review.assigned_at,
        started_at=context.review.started_at,
        priority_reason=priority_reason(context.review, context.version),
        material_status=material_state.status,
    )


def add_event(
    session: Session, event_type: str, aggregate_type: str, aggregate_id: uuid.UUID
) -> None:
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
    review: Review,
    details: dict[str, object],
) -> None:
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action=action,
            resource_type="review",
            resource_id=review.id,
            result="SUCCESS",
            request_id=request.state.request_id,
            details=details,
        )
    )


@router.get("/reviews", response_model=ReviewQueueResponse)
def review_queue(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.REVIEWER)
    rows = session.execute(
        select(
            Review,
            Assignment,
            Submission,
            SubmissionVersion,
            Enrollment,
            User,
            TaskDefinition,
            TaskVersion,
        )
        .join(Assignment, Assignment.id == Review.assignment_id)
        .join(Submission, Submission.id == Review.submission_id)
        .join(SubmissionVersion, SubmissionVersion.id == Review.submission_version_id)
        .join(Enrollment, Enrollment.id == Assignment.enrollment_id)
        .join(User, User.id == Enrollment.learner_id)
        .join(TaskDefinition, TaskDefinition.id == Assignment.task_definition_id)
        .join(TaskVersion, TaskVersion.id == Assignment.task_version_id)
        .where(
            Review.organization_id == actor.organization_id,
            Review.reviewer_id == actor.id,
            Review.status.in_([ReviewStatus.ASSIGNED, ReviewStatus.IN_REVIEW]),
            Assignment.organization_id == actor.organization_id,
            Submission.organization_id == actor.organization_id,
            Enrollment.organization_id == actor.organization_id,
            User.organization_id == actor.organization_id,
            TaskDefinition.organization_id == actor.organization_id,
            TaskVersion.organization_id == actor.organization_id,
        )
        .order_by(
            case(
                (Review.status == ReviewStatus.IN_REVIEW, 0),
                (SubmissionVersion.version_no > 1, 1),
                else_=2,
            ),
            Review.assigned_at,
            Review.id,
        )
    ).all()
    items: list[ReviewQueueItemOut] = []
    for row in rows:
        context = ReviewContext(*row, None)
        items.append(queue_item(session, context))
    return envelope(request, ReviewQueueOut(items=items))


@router.get("/reviews/{review_id}", response_model=ReviewDetailResponse)
def review_detail(
    review_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.REVIEWER)
    context = get_scoped_context(session, actor, review_id)
    materials = review_materials(session, context)
    base = queue_item(session, context, materials=materials).model_dump()
    return envelope(
        request,
        ReviewDetailOut(
            **base,
            submission_body=context.version.body,
            task_purpose=context.task.purpose,
            completion_criteria=list(context.task.completion_criteria),
            required_deliverables=list(context.task.required_deliverables),
            rubric=context.task.rubric,
            materials=materials,
            finalized_at=context.review.finalized_at,
            evaluation=(
                evaluation_out(context.evaluation)
                if context.evaluation is not None
                else None
            ),
        ),
    )


@router.post("/reviews/{review_id}/start", response_model=ReviewMutationResponse)
def start_review(
    review_id: uuid.UUID,
    command: RevisionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.REVIEWER)
    context = lock_scoped_context(session, actor, review_id)
    payload = {
        **command.model_dump(mode="json"),
        "review_id": str(review_id),
    }
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="review.start",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, ReviewMutationOut(**replay))
    ensure_revision(context.review.revision, command.expected_revision)
    if context.review.status != ReviewStatus.ASSIGNED:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前评审不能开始。")
    if context.assignment.status != AssignmentStatus.SUBMITTED:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "对应任务不在待评审状态。")
    context.review.status = ReviewStatus.IN_REVIEW
    context.review.started_at = datetime.now(UTC)
    context.review.revision += 1
    context.assignment.status = AssignmentStatus.IN_REVIEW
    context.assignment.revision += 1
    result = ReviewMutationOut(
        review_id=context.review.id,
        review_status=context.review.status.value,
        review_revision=context.review.revision,
        assignment_id=context.assignment.id,
        assignment_status=context.assignment.status.value,
        assignment_revision=context.assignment.revision,
    )
    store_result(
        session,
        actor_id=actor.id,
        command="review.start",
        key=idempotency_key,
        payload=payload,
        response=result.model_dump(mode="json"),
    )
    add_event(session, "review.started.v1", "review", context.review.id)
    add_audit(
        session,
        request=request,
        actor=actor,
        action="review.started",
        review=context.review,
        details={
            "assignment_id": str(context.assignment.id),
            "submission_version_id": str(context.version.id),
        },
    )
    session.commit()
    return envelope(request, result)


@router.post("/reviews/{review_id}/finalize", response_model=ReviewMutationResponse)
def finalize_review(
    review_id: uuid.UUID,
    command: FinalizeReviewCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.REVIEWER)
    context = lock_scoped_context(session, actor, review_id)
    payload = {
        **command.model_dump(mode="json"),
        "review_id": str(review_id),
    }
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="review.finalize",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, ReviewMutationOut(**replay))
    ensure_revision(context.review.revision, command.expected_revision)
    if context.review.status != ReviewStatus.IN_REVIEW:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前评审不能提交最终结论。")
    if context.assignment.status != AssignmentStatus.IN_REVIEW:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "对应任务不在评审中。")

    materials = review_materials(session, context)
    if materials.status != "COMPLETE":
        raise ApiError(
            422,
            "MATERIALS_INCOMPLETE",
            "评审材料不完整，不能提交最终结论。",
            details={"missing_items": materials.missing_items},
        )
    configured_dimensions = context.task.rubric.get("dimensions", [])
    required_keys = {
        str(item.get("dimension_key"))
        for item in configured_dimensions
        if isinstance(item, dict) and item.get("required") is True
    }
    submitted_keys = {item.dimension_key for item in command.rubric_evaluations}
    if submitted_keys != required_keys:
        raise ApiError(422, "VALIDATION_FAILED", "固定 Rubric 的必填维度必须全部填写。")
    all_meet = all(
        item.rating == "MEETS" for item in command.rubric_evaluations
    )
    if command.overall_decision == "APPROVE" and not all_meet:
        raise ApiError(422, "VALIDATION_FAILED", "只有全部 Rubric 达标才能通过。")
    if command.overall_decision == "REQUEST_REVISION" and all_meet:
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "要求修订时至少一个 Rubric 维度应标记为待改进。",
        )

    decision = (
        Decision.PASS
        if command.overall_decision == "APPROVE"
        else Decision.REVISION_REQUIRED
    )
    evaluation = Evaluation(
        id=uuid.uuid4(),
        review_id=context.review.id,
        organization_id=context.review.organization_id,
        assignment_id=context.review.assignment_id,
        submission_id=context.review.submission_id,
        submission_version_id=context.review.submission_version_id,
        reviewer_id=context.review.reviewer_id,
        review_revision=command.expected_revision,
        decision=decision,
        rubric_scores={
            item.dimension_key: item.rating for item in command.rubric_evaluations
        },
        structured_feedback=[
            item.model_dump(mode="json") for item in command.rubric_evaluations
        ],
        feedback_structure_version=1,
        feedback=command.overall_feedback,
        created_by=actor.id,
    )
    session.add(evaluation)
    context.review.status = ReviewStatus.FINALIZED
    context.review.finalized_at = datetime.now(UTC)
    context.review.revision += 1
    if decision == Decision.PASS:
        context.assignment.status = AssignmentStatus.COMPLETED
        if context.enrollment.status != EnrollmentStatus.ACTIVE:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "任务缺少有效 Enrollment。")
        context.enrollment.status = EnrollmentStatus.COMPLETED
        context.enrollment.revision += 1
        create_pass_outcome_bundle(
            session,
            enrollment=context.enrollment,
            assignment=context.assignment,
            evaluation=evaluation,
            reviewer_id=actor.id,
            request_id=request.state.request_id,
        )
        assignment_event = "assignment.completed.v1"
    else:
        context.assignment.status = AssignmentStatus.NEEDS_REVISION
        assignment_event = "assignment.revision_requested.v1"
    context.assignment.revision += 1
    result = ReviewMutationOut(
        review_id=context.review.id,
        review_status=context.review.status.value,
        review_revision=context.review.revision,
        assignment_id=context.assignment.id,
        assignment_status=context.assignment.status.value,
        assignment_revision=context.assignment.revision,
        evaluation_id=evaluation.id,
        decision=evaluation.decision.value,
    )
    store_result(
        session,
        actor_id=actor.id,
        command="review.finalize",
        key=idempotency_key,
        payload=payload,
        response=result.model_dump(mode="json"),
    )
    add_event(session, "review.finalized.v1", "review", context.review.id)
    add_event(session, assignment_event, "assignment", context.assignment.id)
    add_audit(
        session,
        request=request,
        actor=actor,
        action="review.finalized",
        review=context.review,
        details={
            "assignment_id": str(context.assignment.id),
            "submission_version_id": str(context.version.id),
            "decision": evaluation.decision.value,
            "rubric_dimensions": len(command.rubric_evaluations),
            "overall_feedback_characters": len(command.overall_feedback),
        },
    )
    session.commit()
    return envelope(request, result)
