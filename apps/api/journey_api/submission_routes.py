from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from journey_api.attachments import (
    MAX_ATTACHMENT_SIZE_BYTES,
    digest_bytes,
    download_disposition,
    local_scan_clean,
    safe_original_filename,
    storage,
    validate_content,
)
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
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    OutboxEvent,
    OutboxStatus,
    Review,
    ReviewStatus,
    Role,
    Submission,
    SubmissionDraft,
    SubmissionVersion,
    SubmissionVersionAttachment,
    TaskVersion,
    User,
)
from journey_api.schemas import (
    AttachmentResponse,
    CompleteAttachmentCommand,
    PresignAttachmentCommand,
    PresignedAttachmentOut,
    PresignedAttachmentResponse,
    SaveSubmissionDraftCommand,
    SubmissionDraftOut,
    SubmissionDraftResponse,
    SubmissionHistoryResponse,
    SubmissionMutationOut,
    SubmissionMutationResponse,
    SubmissionCommand,
)
from journey_api.submission_service import (
    attachment_out,
    lock_ready_attachments,
    submission_out,
)


api = APIRouter(prefix="/api/v1")


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


def lock_learner_assignment(
    session: Session, actor: Actor, assignment_id: uuid.UUID
) -> Assignment:
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


def lock_owned_attachment(
    session: Session, actor: Actor, attachment_id: uuid.UUID
) -> Attachment:
    attachment = session.scalar(
        select(Attachment)
        .where(
            Attachment.id == attachment_id,
            Attachment.organization_id == actor.organization_id,
            Attachment.owner_id == actor.id,
        )
        .with_for_update()
    )
    if attachment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的附件。")
    return attachment


@api.post(
    "/attachments/presign",
    response_model=PresignedAttachmentResponse,
    responses={413: {"description": "ATTACHMENT_TOO_LARGE"}},
)
def presign_attachment(
    command: PresignAttachmentCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    payload = command.model_dump(mode="json")
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="attachment.presign",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        attachment = session.get(Attachment, uuid.UUID(str(replay["id"])))
        if attachment is None or attachment.owner_id != actor.id:
            raise ApiError(409, "VERSION_CONFLICT", "幂等附件引用已不可用。")
        return envelope(
            request,
            PresignedAttachmentOut(
                **attachment_out(attachment).model_dump(),
                upload_method="PUT",
                upload_url=f"/api/v1/attachments/{attachment.id}/content",
                idempotency_replay=True,
            ),
        )
    assignment = lock_learner_assignment(session, actor, command.assignment_id)
    if assignment.status not in {
        AssignmentStatus.IN_PROGRESS,
        AssignmentStatus.NEEDS_REVISION,
    }:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前任务不能上传附件。")
    task = session.get(TaskVersion, assignment.task_version_id)
    if command.size_bytes > MAX_ATTACHMENT_SIZE_BYTES or (
        task is not None and command.size_bytes > task.max_attachment_size_bytes
    ):
        raise ApiError(413, "ATTACHMENT_TOO_LARGE", "附件超过允许大小。")
    if task is None or command.content_type not in task.allowed_attachment_types:
        raise ApiError(422, "VALIDATION_FAILED", "当前任务不允许这个附件类型或大小。")
    filename = safe_original_filename(command.original_filename, command.content_type)
    attachment_id = uuid.uuid4()
    attachment = Attachment(
        id=attachment_id,
        organization_id=actor.organization_id,
        owner_id=actor.id,
        assignment_id=assignment.id,
        purpose=command.purpose,
        original_filename=filename,
        storage_key=(
            f"attachments/{actor.organization_id.hex}/{actor.id.hex}/{attachment_id.hex}"
        ),
        content_type=command.content_type,
        size_bytes=command.size_bytes,
        sha256=command.sha256,
        status=AttachmentStatus.PENDING_UPLOAD,
        scan_status=AttachmentScanStatus.PENDING,
    )
    session.add(attachment)
    store_result(
        session,
        actor_id=actor.id,
        command="attachment.presign",
        key=idempotency_key,
        payload=payload,
        response={"id": str(attachment.id)},
    )
    add_audit(
        session,
        request=request,
        actor=actor,
        action="attachment.upload_intent_created",
        resource_type="attachment",
        resource_id=attachment.id,
        details={
            "assignment_id": str(assignment.id),
            "purpose": attachment.purpose,
            "content_type": attachment.content_type,
            "size_bytes": attachment.size_bytes,
        },
    )
    session.commit()
    return envelope(
        request,
        PresignedAttachmentOut(
            **attachment_out(attachment).model_dump(),
            upload_method="PUT",
            upload_url=f"/api/v1/attachments/{attachment.id}/content",
        ),
    )


@api.put(
    "/attachments/{attachment_id}/content",
    response_model=AttachmentResponse,
    responses={413: {"description": "ATTACHMENT_TOO_LARGE"}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "text/plain": {"schema": {"type": "string", "format": "binary"}},
                "application/pdf": {
                    "schema": {"type": "string", "format": "binary"}
                },
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
async def upload_attachment_content(
    attachment_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    attachment = lock_owned_attachment(session, actor, attachment_id)
    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            length = int(declared_length)
        except ValueError as exc:
            raise ApiError(400, "INVALID_REQUEST", "Content-Length 无效。") from exc
        if length > attachment.size_bytes or length > MAX_ATTACHMENT_SIZE_BYTES:
            raise ApiError(413, "ATTACHMENT_TOO_LARGE", "附件超过允许大小。")
    if request.headers.get("content-type", "").split(";", 1)[0] != attachment.content_type:
        raise ApiError(422, "VALIDATION_FAILED", "上传内容类型与上传意图不一致。")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > attachment.size_bytes or total > MAX_ATTACHMENT_SIZE_BYTES:
            raise ApiError(413, "ATTACHMENT_TOO_LARGE", "附件超过允许大小。")
        chunks.append(chunk)
    content = b"".join(chunks)
    if total != attachment.size_bytes or digest_bytes(content) != attachment.sha256:
        raise ApiError(422, "VALIDATION_FAILED", "附件大小或 SHA-256 与上传意图不一致。")
    validate_content(content, attachment.content_type)
    if attachment.status in {AttachmentStatus.UPLOADED, AttachmentStatus.READY}:
        return envelope(request, attachment_out(attachment))
    if attachment.status != AttachmentStatus.PENDING_UPLOAD:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前附件不能接收上传内容。")
    storage.put(attachment.storage_key, content)
    attachment.status = AttachmentStatus.UPLOADED
    attachment.uploaded_at = func.now()
    session.commit()
    return envelope(request, attachment_out(attachment))


@api.post("/attachments/{attachment_id}/complete", response_model=AttachmentResponse)
def complete_attachment(
    attachment_id: uuid.UUID,
    command: CompleteAttachmentCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    payload = {**command.model_dump(mode="json"), "attachment_id": str(attachment_id)}
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="attachment.complete",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        attachment = session.get(Attachment, attachment_id)
        if attachment is None or attachment.owner_id != actor.id:
            raise ApiError(409, "VERSION_CONFLICT", "幂等附件引用已不可用。")
        return envelope(request, attachment_out(attachment))
    attachment = lock_owned_attachment(session, actor, attachment_id)
    if (
        command.size_bytes != attachment.size_bytes
        or command.content_type != attachment.content_type
        or command.sha256 != attachment.sha256
    ):
        raise ApiError(422, "VALIDATION_FAILED", "附件完成元数据与上传意图不一致。")
    if attachment.status == AttachmentStatus.READY:
        result = attachment_out(attachment)
        store_result(
            session,
            actor_id=actor.id,
            command="attachment.complete",
            key=idempotency_key,
            payload=payload,
            response={"id": str(attachment.id)},
        )
        session.commit()
        return envelope(request, result)
    if attachment.status != AttachmentStatus.UPLOADED:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "附件尚未上传或已被拒绝。")
    content = storage.get(attachment.storage_key)
    if len(content) != attachment.size_bytes or digest_bytes(content) != attachment.sha256:
        raise ApiError(422, "VALIDATION_FAILED", "存储中的附件校验失败。")
    validate_content(content, attachment.content_type)
    clean = local_scan_clean(content)
    attachment.status = AttachmentStatus.READY if clean else AttachmentStatus.REJECTED
    attachment.scan_status = (
        AttachmentScanStatus.LOCAL_CLEAN
        if clean
        else AttachmentScanStatus.LOCAL_REJECTED
    )
    attachment.completed_at = func.now()
    if clean:
        store_result(
            session,
            actor_id=actor.id,
            command="attachment.complete",
            key=idempotency_key,
            payload=payload,
            response={"id": str(attachment.id)},
        )
    add_audit(
        session,
        request=request,
        actor=actor,
        action="attachment.local_scan_completed",
        resource_type="attachment",
        resource_id=attachment.id,
        details={"local_scan_result": attachment.scan_status.value},
    )
    session.commit()
    if not clean:
        raise ApiError(422, "VALIDATION_FAILED", "附件未通过本地隔离扫描，不能提交。")
    return envelope(request, attachment_out(attachment))


@api.delete("/attachments/{attachment_id}", response_model=AttachmentResponse)
def delete_attachment(
    attachment_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    attachment = lock_owned_attachment(session, actor, attachment_id)
    linked = session.scalar(
        select(SubmissionVersionAttachment.attachment_id).where(
            SubmissionVersionAttachment.attachment_id == attachment.id
        )
    )
    if linked is not None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已绑定历史版本的附件不能删除。")
    attachment.status = AttachmentStatus.DELETED
    storage.delete(attachment.storage_key)
    add_audit(
        session,
        request=request,
        actor=actor,
        action="attachment.deleted",
        resource_type="attachment",
        resource_id=attachment.id,
        details={"assignment_id": str(attachment.assignment_id)},
    )
    session.commit()
    return envelope(request, attachment_out(attachment))


@api.get(
    "/attachments/{attachment_id}/download",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
def download_attachment(
    attachment_id: uuid.UUID,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> Response:
    attachment = session.scalar(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.organization_id == actor.organization_id,
            Attachment.status == AttachmentStatus.READY,
        )
    )
    if attachment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的附件。")
    allowed = actor.role == Role.LEARNER and attachment.owner_id == actor.id
    if actor.role == Role.REVIEWER:
        allowed = session.scalar(
            select(Review.id)
            .join(
                SubmissionVersionAttachment,
                SubmissionVersionAttachment.submission_version_id
                == Review.submission_version_id,
            )
            .where(
                SubmissionVersionAttachment.attachment_id == attachment.id,
                Review.organization_id == actor.organization_id,
                Review.reviewer_id == actor.id,
            )
        ) is not None
    if not allowed:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的附件。")
    content = storage.get(attachment.storage_key)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": download_disposition(attachment.original_filename)},
    )


@api.put(
    "/me/assignments/{assignment_id}/draft", response_model=SubmissionDraftResponse
)
def save_submission_draft(
    assignment_id: uuid.UUID,
    command: SaveSubmissionDraftCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    payload = {**command.model_dump(mode="json"), "assignment_id": str(assignment_id)}
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="submission.draft.save",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, SubmissionDraftOut(**replay))
    assignment = lock_learner_assignment(session, actor, assignment_id)
    ensure_revision(assignment.revision, command.expected_revision)
    if assignment.status not in {
        AssignmentStatus.IN_PROGRESS,
        AssignmentStatus.NEEDS_REVISION,
    }:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前任务不能保存草稿。")
    task = session.get(TaskVersion, assignment.task_version_id)
    if task is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "任务缺少固定内容版本。")
    lock_ready_attachments(
        session,
        actor=actor,
        assignment_id=assignment.id,
        task=task,
        attachment_ids=command.attachment_ids,
    )
    draft = session.scalar(
        select(SubmissionDraft)
        .where(SubmissionDraft.assignment_id == assignment.id)
        .with_for_update()
    )
    if draft is None:
        draft = SubmissionDraft(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            assignment_id=assignment.id,
            owner_id=actor.id,
            body=command.body,
            attachment_ids=[str(value) for value in command.attachment_ids],
            revision=1,
        )
        session.add(draft)
    else:
        if draft.owner_id != actor.id or draft.organization_id != actor.organization_id:
            raise ApiError(404, "NOT_FOUND", "没有找到可访问的草稿。")
        draft.body = command.body
        draft.attachment_ids = [str(value) for value in command.attachment_ids]
        draft.revision += 1
        draft.updated_at = func.now()
    session.flush()
    result = SubmissionDraftOut(
        body=draft.body,
        attachment_ids=[uuid.UUID(value) for value in draft.attachment_ids],
        revision=draft.revision,
        updated_at=draft.updated_at,
    )
    store_result(
        session,
        actor_id=actor.id,
        command="submission.draft.save",
        key=idempotency_key,
        payload=payload,
        response=result.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, result)


@api.post(
    "/me/assignments/{assignment_id}/submissions",
    response_model=SubmissionMutationResponse,
)
def submit_assignment(
    assignment_id: uuid.UUID,
    command: SubmissionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    payload = {**command.model_dump(mode="json"), "assignment_id": str(assignment_id)}
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="assignment.submit",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, SubmissionMutationOut(**replay))
    assignment = lock_learner_assignment(session, actor, assignment_id)
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="assignment.submit",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, SubmissionMutationOut(**replay))
    ensure_revision(assignment.revision, command.expected_revision)
    if assignment.status not in {
        AssignmentStatus.IN_PROGRESS,
        AssignmentStatus.NEEDS_REVISION,
    }:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前任务不能提交。")
    task = session.get(TaskVersion, assignment.task_version_id)
    if task is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "任务缺少固定内容版本。")
    attachments = lock_ready_attachments(
        session,
        actor=actor,
        assignment_id=assignment.id,
        task=task,
        attachment_ids=command.attachment_ids,
    )
    submission = session.scalar(
        select(Submission)
        .where(Submission.assignment_id == assignment.id)
        .with_for_update()
    )
    if submission is None:
        submission = Submission(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            assignment_id=assignment.id,
            current_version_no=0,
        )
        session.add(submission)
        session.flush()
    version_no = submission.current_version_no + 1
    version = SubmissionVersion(
        id=uuid.uuid4(),
        submission_id=submission.id,
        version_no=version_no,
        body=command.body.strip(),
        created_by=actor.id,
    )
    session.add(version)
    session.flush()
    for position, attachment in enumerate(attachments, start=1):
        session.add(
            SubmissionVersionAttachment(
                submission_id=submission.id,
                submission_version_id=version.id,
                attachment_id=attachment.id,
                organization_id=assignment.organization_id,
                assignment_id=assignment.id,
                position=position,
            )
        )
    enrollment = session.get(Enrollment, assignment.enrollment_id)
    if enrollment is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "任务缺少有效 Enrollment。")
    review = Review(
        id=uuid.uuid4(),
        organization_id=assignment.organization_id,
        assignment_id=assignment.id,
        submission_id=submission.id,
        submission_version_id=version.id,
        reviewer_id=enrollment.reviewer_id,
        status=ReviewStatus.ASSIGNED,
        revision=1,
    )
    session.add(review)
    submission.current_version_no = version_no
    assignment.status = AssignmentStatus.SUBMITTED
    assignment.revision += 1
    session.execute(
        delete(SubmissionDraft).where(SubmissionDraft.assignment_id == assignment.id)
    )
    result = SubmissionMutationOut(
        assignment_id=assignment.id,
        assignment_status=assignment.status.value,
        assignment_revision=assignment.revision,
        submission_id=submission.id,
        submission_version_id=version.id,
        version_no=version.version_no,
        attachment_ids=[item.id for item in attachments],
    )
    store_result(
        session,
        actor_id=actor.id,
        command="assignment.submit",
        key=idempotency_key,
        payload=payload,
        response=result.model_dump(mode="json"),
    )
    add_event(session, "submission.created.v1", "submission", submission.id)
    add_audit(
        session,
        request=request,
        actor=actor,
        action="submission.version_created",
        resource_type="submission_version",
        resource_id=version.id,
        details={
            "assignment_id": str(assignment.id),
            "submission_id": str(submission.id),
            "version_no": version.version_no,
            "attachment_count": len(attachments),
        },
    )
    session.commit()
    return envelope(request, result)


@api.get("/me/submissions/{submission_id}", response_model=SubmissionHistoryResponse)
def submission_history(
    submission_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    submission = session.scalar(
        select(Submission)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(Enrollment, Enrollment.id == Assignment.enrollment_id)
        .where(
            Submission.id == submission_id,
            Submission.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
        )
    )
    if submission is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的提交历史。")
    return envelope(request, submission_out(session, submission))


router = APIRouter()
router.include_router(api)
