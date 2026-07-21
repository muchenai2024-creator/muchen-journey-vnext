from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.auth import Actor
from journey_api.errors import ApiError
from journey_api.models import (
    Attachment,
    AttachmentStatus,
    Evaluation,
    Review,
    Submission,
    SubmissionDraft,
    SubmissionVersion,
    SubmissionVersionAttachment,
    TaskVersion,
)
from journey_api.schemas import (
    AttachmentOut,
    SubmissionDraftOut,
    SubmissionOut,
    SubmissionVersionOut,
)


def attachment_out(attachment: Attachment) -> AttachmentOut:
    return AttachmentOut(
        id=attachment.id,
        assignment_id=attachment.assignment_id,
        purpose=attachment.purpose,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        status=attachment.status.value,
        scan_status=attachment.scan_status.value,
    )


def submission_out(session: Session, submission: Submission) -> SubmissionOut:
    rows = session.execute(
        select(SubmissionVersion, Review, Evaluation)
        .outerjoin(Review, Review.submission_version_id == SubmissionVersion.id)
        .outerjoin(Evaluation, Evaluation.review_id == Review.id)
        .where(SubmissionVersion.submission_id == submission.id)
        .order_by(SubmissionVersion.version_no)
    ).all()
    attachments_by_version: dict[uuid.UUID, list[AttachmentOut]] = {}
    attachment_rows = session.execute(
        select(SubmissionVersionAttachment, Attachment)
        .join(Attachment, Attachment.id == SubmissionVersionAttachment.attachment_id)
        .where(SubmissionVersionAttachment.submission_id == submission.id)
        .order_by(
            SubmissionVersionAttachment.submission_version_id,
            SubmissionVersionAttachment.position,
        )
    ).all()
    for link, attachment in attachment_rows:
        attachments_by_version.setdefault(link.submission_version_id, []).append(
            attachment_out(attachment)
        )
    return SubmissionOut(
        id=submission.id,
        assignment_id=submission.assignment_id,
        current_version_no=submission.current_version_no,
        versions=[
            SubmissionVersionOut(
                id=version.id,
                version_no=version.version_no,
                body=version.body,
                created_at=version.created_at,
                attachments=attachments_by_version.get(version.id, []),
                review_id=review.id if review is not None else None,
                review_status=review.status.value if review is not None else None,
                decision=evaluation.decision.value if evaluation is not None else None,
                feedback=evaluation.feedback if evaluation is not None else None,
            )
            for version, review, evaluation in rows
        ],
    )


def assignment_workspace(
    session: Session, actor: Actor, assignment_id: uuid.UUID
) -> tuple[SubmissionOut | None, SubmissionDraftOut | None, list[AttachmentOut], str | None]:
    submission = session.scalar(
        select(Submission).where(
            Submission.assignment_id == assignment_id,
            Submission.organization_id == actor.organization_id,
        )
    )
    history = submission_out(session, submission) if submission is not None else None
    draft = session.scalar(
        select(SubmissionDraft).where(
            SubmissionDraft.assignment_id == assignment_id,
            SubmissionDraft.organization_id == actor.organization_id,
            SubmissionDraft.owner_id == actor.id,
        )
    )
    draft_out = (
        SubmissionDraftOut(
            body=draft.body,
            attachment_ids=[uuid.UUID(value) for value in draft.attachment_ids],
            revision=draft.revision,
            updated_at=draft.updated_at,
        )
        if draft is not None
        else None
    )
    linked_ids = select(SubmissionVersionAttachment.attachment_id)
    available = session.scalars(
        select(Attachment)
        .where(
            Attachment.organization_id == actor.organization_id,
            Attachment.owner_id == actor.id,
            Attachment.assignment_id == assignment_id,
            Attachment.status == AttachmentStatus.READY,
            Attachment.id.not_in(linked_ids),
        )
        .order_by(Attachment.created_at, Attachment.id)
    ).all()
    latest_feedback = None
    if history is not None:
        for version in reversed(history.versions):
            if version.decision == "REVISION_REQUIRED" and version.feedback:
                latest_feedback = version.feedback
                break
    return history, draft_out, [attachment_out(item) for item in available], latest_feedback


def lock_ready_attachments(
    session: Session,
    *,
    actor: Actor,
    assignment_id: uuid.UUID,
    task: TaskVersion,
    attachment_ids: list[uuid.UUID],
) -> list[Attachment]:
    if not attachment_ids:
        return []
    attachments = list(
        session.scalars(
            select(Attachment)
            .where(Attachment.id.in_(attachment_ids))
            .order_by(Attachment.id)
            .with_for_update()
        ).all()
    )
    if len(attachments) != len(attachment_ids):
        raise ApiError(422, "VALIDATION_FAILED", "一个或多个附件不可用于本次提交。")
    linked = set(
        session.scalars(
            select(SubmissionVersionAttachment.attachment_id).where(
                SubmissionVersionAttachment.attachment_id.in_(attachment_ids)
            )
        )
    )
    allowed_types = set(task.allowed_attachment_types)
    for attachment in attachments:
        if (
            attachment.organization_id != actor.organization_id
            or attachment.owner_id != actor.id
            or attachment.assignment_id != assignment_id
            or attachment.purpose != "SUBMISSION_EVIDENCE"
            or attachment.status != AttachmentStatus.READY
            or attachment.id in linked
            or attachment.content_type not in allowed_types
            or attachment.size_bytes > task.max_attachment_size_bytes
        ):
            raise ApiError(422, "VALIDATION_FAILED", "一个或多个附件不可用于本次提交。")
    by_id = {attachment.id: attachment for attachment in attachments}
    return [by_id[attachment_id] for attachment_id in attachment_ids]
