from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from journey_api.db import Base


class UserStatus(str, enum.Enum):
    PENDING_IDENTITY = "PENDING_IDENTITY"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class Role(str, enum.Enum):
    LEARNER = "LEARNER"
    REVIEWER = "REVIEWER"
    OPERATOR = "OPERATOR"


class EnrollmentStatus(str, enum.Enum):
    PENDING_IDENTITY = "PENDING_IDENTITY"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class InviteStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class JoinContextStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REVOKED = "REVOKED"


class AssignmentStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    NEEDS_REVISION = "NEEDS_REVISION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskDefinitionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class ReviewStatus(str, enum.Enum):
    ASSIGNED = "ASSIGNED"
    IN_REVIEW = "IN_REVIEW"
    FINALIZED = "FINALIZED"


class Decision(str, enum.Enum):
    PASS = "PASS"
    REVISION_REQUIRED = "REVISION_REQUIRED"


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"


class HandoffStatus(str, enum.Enum):
    READY = "READY"


class NotificationChannel(str, enum.Enum):
    LOCAL_TEST = "LOCAL_TEST"
    FEISHU = "FEISHU"
    EMAIL = "EMAIL"


class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    DELIVERED = "DELIVERED"
    RETRY_WAIT = "RETRY_WAIT"
    DEAD = "DEAD"


class NotificationAttemptStatus(str, enum.Enum):
    DELIVERED = "DELIVERED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    LEASE_EXPIRED = "LEASE_EXPIRED"


class AttachmentStatus(str, enum.Enum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    UPLOADED = "UPLOADED"
    READY = "READY"
    REJECTED = "REJECTED"
    DELETED = "DELETED"


class AttachmentScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    LOCAL_CLEAN = "LOCAL_CLEAN"
    LOCAL_REJECTED = "LOCAL_REJECTED"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus, native_enum=False), default=UserStatus.ACTIVE)


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_role_assignments_user_role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))


class ExternalIdentity(Base):
    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_external_identity_provider_subject"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(180))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    task_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_versions.id"))
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[InviteStatus] = mapped_column(Enum(InviteStatus, native_enum=False), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    consumed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JoinContext(Base):
    __tablename__ = "join_contexts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    invite_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invites.id"), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[JoinContextStatus] = mapped_column(Enum(JoinContextStatus, native_enum=False))
    created_user: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdentitySession(Base):
    __tablename__ = "identity_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    result: Mapped[str] = mapped_column(String(32))
    request_id: Mapped[str] = mapped_column(String(100), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        UniqueConstraint("scope", "subject_hash", "window_started_at", name="uq_auth_rate_limit_window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    scope: Mapped[str] = mapped_column(String(60))
    subject_hash: Mapped[str] = mapped_column(String(64))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=1)


class TaskDefinition(Base):
    __tablename__ = "task_definitions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "stable_key", name="uq_task_definitions_organization_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    stable_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[TaskDefinitionStatus] = mapped_column(
        Enum(TaskDefinitionStatus, native_enum=False)
    )
    revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TaskVersion(Base):
    __tablename__ = "task_versions"
    __table_args__ = (
        UniqueConstraint(
            "task_definition_id", "version", name="uq_task_versions_definition_version"
        ),
        UniqueConstraint(
            "id", "task_definition_id", name="uq_task_versions_id_definition"
        ),
        CheckConstraint("version >= 1", name="ck_task_versions_positive_version"),
        CheckConstraint(
            "estimated_duration_minutes BETWEEN 1 AND 480",
            name="ck_task_versions_estimated_duration",
        ),
        CheckConstraint(
            "feedback_sla_business_days BETWEEN 1 AND 10",
            name="ck_task_versions_feedback_sla",
        ),
        CheckConstraint(
            "max_attachment_size_bytes >= 0",
            name="ck_task_versions_attachment_size",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    task_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_definitions.id"), index=True
    )
    version: Mapped[int]
    title: Mapped[str] = mapped_column(String(180))
    purpose: Mapped[str] = mapped_column(Text)
    learner_outcome: Mapped[str] = mapped_column(Text)
    instructions: Mapped[list[str]] = mapped_column(JSON)
    completion_criteria: Mapped[list[str]] = mapped_column(JSON)
    required_deliverables: Mapped[list[str]] = mapped_column(JSON)
    content_source_notes: Mapped[list[str]] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(Text)
    reviewer_calibration_note: Mapped[str] = mapped_column(Text)
    allowed_attachment_types: Mapped[list[str]] = mapped_column(JSON)
    max_attachment_size_bytes: Mapped[int] = mapped_column(default=0)
    reference_materials: Mapped[list[str]] = mapped_column(JSON)
    estimated_duration_minutes: Mapped[int]
    rubric: Mapped[dict[str, Any]] = mapped_column(JSON)
    rubric_version: Mapped[int]
    reviewer_role: Mapped[str] = mapped_column(String(40))
    feedback_sla_business_days: Mapped[int]
    sensitivity: Mapped[str] = mapped_column(String(40))
    audience: Mapped[str] = mapped_column(String(40))
    published_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "learner_id",
            name="uq_enrollments_fixed_owner_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[EnrollmentStatus] = mapped_column(Enum(EnrollmentStatus, native_enum=False))
    revision: Mapped[int] = mapped_column(default=1)


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_version_id", "task_definition_id"],
            ["task_versions.id", "task_versions.task_definition_id"],
            name="fk_assignments_task_version_definition",
        ),
        UniqueConstraint(
            "enrollment_id", "task_definition_id", name="uq_assignments_enrollment_task"
        ),
        UniqueConstraint("enrollment_id", "position", name="uq_assignments_enrollment_position"),
        CheckConstraint("position >= 1", name="ck_assignments_positive_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"), index=True)
    task_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_definitions.id"))
    task_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_versions.id"))
    position: Mapped[int] = mapped_column(default=1)
    status: Mapped[AssignmentStatus] = mapped_column(Enum(AssignmentStatus, native_enum=False))
    revision: Mapped[int] = mapped_column(default=1)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_submissions_assignment_organization",
        ),
        UniqueConstraint("assignment_id", name="uq_submissions_assignment"),
        UniqueConstraint(
            "id",
            "organization_id",
            "assignment_id",
            name="uq_submissions_id_organization_assignment",
        ),
        CheckConstraint(
            "current_version_no >= 0", name="ck_submissions_nonnegative_current_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID]
    current_version_no: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SubmissionVersion(Base):
    __tablename__ = "submission_versions"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "version_no", name="uq_submission_versions_submission_version"
        ),
        CheckConstraint("version_no >= 1", name="ck_submission_versions_positive_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    version_no: Mapped[int]
    body: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubmissionDraft(Base):
    __tablename__ = "submission_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_submission_drafts_assignment_organization",
        ),
        ForeignKeyConstraint(
            ["owner_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_submission_drafts_owner_organization",
        ),
        UniqueConstraint("assignment_id", name="uq_submission_drafts_assignment"),
        CheckConstraint("revision >= 1", name="ck_submission_drafts_positive_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID]
    owner_id: Mapped[uuid.UUID]
    body: Mapped[str] = mapped_column(Text)
    attachment_ids: Mapped[list[str]] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_attachments_owner_organization",
        ),
        ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_attachments_assignment_organization",
        ),
        CheckConstraint(
            "purpose IN ('SUBMISSION_EVIDENCE')", name="ck_attachments_purpose"
        ),
        CheckConstraint(
            "size_bytes BETWEEN 1 AND 5242880", name="ck_attachments_size"
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "assignment_id",
            name="uq_attachments_id_organization_assignment",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    original_filename: Mapped[str] = mapped_column(String(180))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[AttachmentStatus] = mapped_column(
        Enum(AttachmentStatus, native_enum=False)
    )
    scan_status: Mapped[AttachmentScanStatus] = mapped_column(
        Enum(AttachmentScanStatus, native_enum=False)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SubmissionVersionAttachment(Base):
    __tablename__ = "submission_version_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["submission_version_id", "submission_id"],
            ["submission_versions.id", "submission_versions.submission_id"],
            name="fk_submission_attachment_version_submission",
        ),
        ForeignKeyConstraint(
            ["submission_id", "organization_id", "assignment_id"],
            [
                "submissions.id",
                "submissions.organization_id",
                "submissions.assignment_id",
            ],
            name="fk_submission_attachment_submission_scope",
        ),
        ForeignKeyConstraint(
            ["attachment_id", "organization_id", "assignment_id"],
            [
                "attachments.id",
                "attachments.organization_id",
                "attachments.assignment_id",
            ],
            name="fk_submission_attachment_file_scope",
        ),
        UniqueConstraint("attachment_id", name="uq_submission_attachment_file"),
        UniqueConstraint(
            "submission_version_id", "position", name="uq_submission_attachment_position"
        ),
        CheckConstraint("position >= 1", name="ck_submission_attachment_position"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    submission_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    attachment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    assignment_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    position: Mapped[int]


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_reviews_assignment_organization",
        ),
        ForeignKeyConstraint(
            ["submission_id", "organization_id", "assignment_id"],
            ["submissions.id", "submissions.organization_id", "submissions.assignment_id"],
            name="fk_reviews_submission_scope",
        ),
        ForeignKeyConstraint(
            ["submission_version_id", "submission_id"],
            ["submission_versions.id", "submission_versions.submission_id"],
            name="fk_reviews_submission_version",
        ),
        ForeignKeyConstraint(
            ["reviewer_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_reviews_reviewer_organization",
        ),
        UniqueConstraint("submission_version_id", name="uq_review_submission_version"),
        UniqueConstraint(
            "id",
            "organization_id",
            "assignment_id",
            "submission_id",
            "submission_version_id",
            "reviewer_id",
            name="uq_reviews_fixed_scope",
        ),
        CheckConstraint("revision >= 1", name="ck_reviews_positive_revision"),
        CheckConstraint(
            "(status = 'ASSIGNED' AND started_at IS NULL AND finalized_at IS NULL) "
            "OR (status = 'IN_REVIEW' AND started_at IS NOT NULL AND finalized_at IS NULL) "
            "OR (status = 'FINALIZED' AND started_at IS NOT NULL AND finalized_at IS NOT NULL)",
            name="ck_reviews_status_timestamps",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    submission_id: Mapped[uuid.UUID]
    submission_version_id: Mapped[uuid.UUID]
    reviewer_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus, native_enum=False))
    revision: Mapped[int] = mapped_column(default=1)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "review_id",
                "organization_id",
                "assignment_id",
                "submission_id",
                "submission_version_id",
                "reviewer_id",
            ],
            [
                "reviews.id",
                "reviews.organization_id",
                "reviews.assignment_id",
                "reviews.submission_id",
                "reviews.submission_version_id",
                "reviews.reviewer_id",
            ],
            name="fk_evaluations_review_fixed_scope",
        ),
        CheckConstraint(
            "created_by = reviewer_id", name="ck_evaluations_reviewer_is_actor"
        ),
        CheckConstraint(
            "review_revision >= 1", name="ck_evaluations_positive_review_revision"
        ),
        CheckConstraint(
            "(feedback_structure_version = 0 AND structured_feedback IS NULL) "
            "OR (feedback_structure_version = 1 AND structured_feedback IS NOT NULL)",
            name="ck_evaluations_feedback_structure",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "assignment_id",
            name="uq_evaluations_outcome_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    review_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID]
    submission_id: Mapped[uuid.UUID]
    submission_version_id: Mapped[uuid.UUID]
    reviewer_id: Mapped[uuid.UUID]
    review_revision: Mapped[int]
    decision: Mapped[Decision] = mapped_column(Enum(Decision, native_enum=False))
    rubric_scores: Mapped[dict[str, str]] = mapped_column(JSON)
    structured_feedback: Mapped[list[dict[str, str]] | None] = mapped_column(
        JSON, nullable=True
    )
    feedback_structure_version: Mapped[int] = mapped_column(default=1)
    feedback: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Outcome(Base):
    __tablename__ = "outcomes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["enrollment_id", "organization_id", "learner_id"],
            ["enrollments.id", "enrollments.organization_id", "enrollments.learner_id"],
            name="fk_outcomes_enrollment_owner_scope",
        ),
        ForeignKeyConstraint(
            ["source_evaluation_id", "organization_id", "assignment_id"],
            ["evaluations.id", "evaluations.organization_id", "evaluations.assignment_id"],
            name="fk_outcomes_evaluation_scope",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "enrollment_id",
            "source_evaluation_id",
            "learner_id",
            name="uq_outcomes_fixed_scope",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "enrollment_id",
            "source_evaluation_id",
            name="uq_outcomes_handoff_scope",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "learner_id",
            name="uq_outcomes_recipient_scope",
        ),
        UniqueConstraint("assignment_id", name="uq_outcomes_assignment"),
        CheckConstraint("status = 'HANDOFF_READY'", name="ck_outcomes_handoff_ready"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    learner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID]
    enrollment_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    source_evaluation_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Handoff(Base):
    __tablename__ = "handoffs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outcome_id", "organization_id", "enrollment_id", "source_evaluation_id"],
            [
                "outcomes.id",
                "outcomes.organization_id",
                "outcomes.enrollment_id",
                "outcomes.source_evaluation_id",
            ],
            name="fk_handoffs_outcome_fixed_scope",
        ),
        ForeignKeyConstraint(
            ["owner_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_handoffs_owner_organization",
        ),
        UniqueConstraint("outcome_id", name="uq_handoffs_outcome"),
        UniqueConstraint("enrollment_id", name="uq_handoffs_enrollment"),
        UniqueConstraint("source_evaluation_id", name="uq_handoffs_evaluation"),
        CheckConstraint("status = 'READY'", name="ck_handoffs_ready"),
        CheckConstraint(
            "next_step_code = 'CONFIRM_HANDOFF'", name="ck_handoffs_next_step"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    enrollment_id: Mapped[uuid.UUID]
    outcome_id: Mapped[uuid.UUID]
    source_evaluation_id: Mapped[uuid.UUID]
    owner_user_id: Mapped[uuid.UUID]
    status: Mapped[HandoffStatus] = mapped_column(
        Enum(HandoffStatus, native_enum=False)
    )
    title: Mapped[str] = mapped_column(String(180))
    next_step_code: Mapped[str] = mapped_column(String(80))
    next_step_title: Mapped[str] = mapped_column(String(240))
    instructions: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_outbox_events_owner_scope",
        ),
        ForeignKeyConstraint(
            ["actor_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_outbox_events_actor_scope",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "owner_id",
            "aggregate_id",
            name="uq_outbox_notification_fixed_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload_version: Mapped[int] = mapped_column(default=1)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[OutboxStatus] = mapped_column(Enum(OutboxStatus, native_enum=False), index=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lock_token: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outcome_id", "organization_id", "recipient_user_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.learner_id"],
            name="fk_notification_deliveries_outcome_recipient",
        ),
        ForeignKeyConstraint(
            ["event_id", "organization_id", "recipient_user_id", "outcome_id"],
            [
                "outbox_events.id",
                "outbox_events.organization_id",
                "outbox_events.owner_id",
                "outbox_events.aggregate_id",
            ],
            name="fk_notification_deliveries_event_scope",
        ),
        UniqueConstraint("event_id", name="uq_notification_deliveries_event"),
        UniqueConstraint(
            "event_id",
            "recipient_user_id",
            "channel",
            "template_version",
            name="uq_notification_deliveries_dedupe",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_notification_deliveries_attempts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    outcome_id: Mapped[uuid.UUID]
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False)
    )
    template_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, native_enum=False), index=True
    )
    attempt_count: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"
    __table_args__ = (
        UniqueConstraint(
            "delivery_id", "attempt_number", name="uq_notification_attempt_number"
        ),
        CheckConstraint("attempt_number >= 1", name="ck_notification_attempt_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_deliveries.id"), index=True
    )
    attempt_number: Mapped[int]
    status: Mapped[NotificationAttemptStatus] = mapped_column(
        Enum(NotificationAttemptStatus, native_enum=False)
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LocalNotificationReceipt(Base):
    __tablename__ = "local_notification_receipts"
    __table_args__ = (
        UniqueConstraint(
            "delivery_id", name="uq_local_notification_receipt_delivery"
        ),
        UniqueConstraint("dedupe_key", name="uq_local_notification_receipt_dedupe"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_deliveries.id")
    )
    dedupe_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(80), primary_key=True)
    release: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("package_id", name="uq_import_batches_package_id"),
        UniqueConstraint("package_checksum", name="uq_import_batches_checksum"),
        UniqueConstraint("id", "organization_id", name="uq_import_batches_fixed_scope"),
        CheckConstraint("schema_version = 1", name="ck_import_batches_schema_v1"),
        CheckConstraint(
            "status IN ('APPLIED', 'APPLIED_WITH_QUARANTINE')",
            name="ck_import_batches_status",
        ),
        CheckConstraint(
            "record_count >= 0 AND imported_count >= 0 AND replayed_count >= 0 "
            "AND quarantined_count >= 0",
            name="ck_import_batches_nonnegative_counts",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    package_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    package_checksum: Mapped[str] = mapped_column(String(64))
    source_revision: Mapped[str] = mapped_column(String(120))
    schema_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(40))
    record_count: Mapped[int]
    imported_count: Mapped[int]
    replayed_count: Mapped[int]
    quarantined_count: Mapped[int]
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ImportRecord(Base):
    __tablename__ = "import_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "organization_id"],
            ["import_batches.id", "import_batches.organization_id"],
            name="fk_import_records_batch_scope",
        ),
        UniqueConstraint("batch_id", "source_key", name="uq_import_records_batch_key"),
        CheckConstraint(
            "status IN ('IMPORTED', 'REPLAYED', 'QUARANTINED')",
            name="ck_import_records_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    source_namespace: Mapped[str] = mapped_column(String(80))
    source_key: Mapped[str] = mapped_column(String(120))
    payload_hash: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(40))
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("actor_id", "command", "key", name="uq_idempotency_actor_command_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    command: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(120))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
