from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RevisionCommand(StrictModel):
    expected_revision: int = Field(ge=1)


class SubmissionCommand(RevisionCommand):
    body: str = Field(min_length=40, max_length=8_000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @field_validator("attachment_ids")
    @classmethod
    def unique_submission_attachments(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Attachment IDs must be unique")
        return values


class SaveSubmissionDraftCommand(RevisionCommand):
    body: str = Field(default="", max_length=8_000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @field_validator("attachment_ids")
    @classmethod
    def unique_draft_attachments(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Attachment IDs must be unique")
        return values


AttachmentContentType = Literal[
    "text/plain", "application/pdf", "image/png", "image/jpeg"
]


class PresignAttachmentCommand(StrictModel):
    assignment_id: UUID
    purpose: Literal["SUBMISSION_EVIDENCE"] = "SUBMISSION_EVIDENCE"
    original_filename: str = Field(min_length=1, max_length=180)
    content_type: AttachmentContentType
    size_bytes: int = Field(ge=1, le=100_000_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CompleteAttachmentCommand(StrictModel):
    size_bytes: int = Field(ge=1, le=5_242_880)
    content_type: AttachmentContentType
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


ReviewerDimensionKey = Literal[
    "problem_clarity", "evidence_quality", "action_feasibility", "validation_design"
]


class RubricEvaluationCommand(StrictModel):
    dimension_key: ReviewerDimensionKey
    rating: Literal["MEETS", "NEEDS_WORK"]
    feedback: str = Field(min_length=5, max_length=500)

    @field_validator("feedback")
    @classmethod
    def normalize_feedback(cls, value: str) -> str:
        return value.strip()


class FinalizeReviewCommand(RevisionCommand):
    overall_decision: Literal["APPROVE", "REQUEST_REVISION"]
    overall_feedback: str = Field(min_length=10, max_length=2_000)
    rubric_evaluations: list[RubricEvaluationCommand] = Field(
        min_length=4, max_length=4
    )

    @field_validator("overall_feedback")
    @classmethod
    def normalize_overall_feedback(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_rubric_dimensions(self) -> "FinalizeReviewCommand":
        expected = {
            "problem_clarity",
            "evidence_quality",
            "action_feasibility",
            "validation_design",
        }
        actual = {item.dimension_key for item in self.rubric_evaluations}
        if actual != expected or len(actual) != len(self.rubric_evaluations):
            raise ValueError("Rubric V1 requires each approved dimension exactly once")
        return self


class CreateInviteCommand(StrictModel):
    purpose: str = Field(min_length=3, max_length=200)
    expires_in_hours: int = Field(ge=1, le=168)
    role: Literal["LEARNER"] = "LEARNER"
    reviewer_id: UUID
    task_version_id: UUID
    target_user_id: UUID | None = None


class RevokeInviteCommand(RevisionCommand):
    reason: str = Field(min_length=10, max_length=500)


class AssignEnrollmentReviewerCommand(RevisionCommand):
    reviewer_id: UUID
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_assignment_reason(cls, value: str) -> str:
        return value.strip()


class CancelEnrollmentCommand(RevisionCommand):
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_cancel_reason(cls, value: str) -> str:
        return value.strip()


class CreateTaskDefinitionCommand(StrictModel):
    stable_key: str = Field(min_length=3, max_length=80, pattern=r"^[A-Z][A-Z0-9_-]+$")

    @field_validator("stable_key")
    @classmethod
    def normalize_stable_key(cls, value: str) -> str:
        return value.strip().upper()


RubricDimensionKey = Literal[
    "problem_clarity", "evidence_quality", "action_feasibility", "validation_design"
]


class RubricDimensionInput(StrictModel):
    dimension_key: RubricDimensionKey
    title: str = Field(min_length=2, max_length=80)
    purpose: str = Field(min_length=5, max_length=500)
    evidence_expected: str = Field(min_length=5, max_length=500)
    levels: dict[Literal["MEETS", "NEEDS_WORK"], str]
    required: Literal[True] = True
    feedback_prompt: str = Field(min_length=5, max_length=500)
    blocking_rule: Literal["REQUIRE_FEEDBACK"] = "REQUIRE_FEEDBACK"

    @model_validator(mode="after")
    def validate_levels(self) -> "RubricDimensionInput":
        if set(self.levels) != {"MEETS", "NEEDS_WORK"}:
            raise ValueError("Rubric levels must contain MEETS and NEEDS_WORK exactly")
        if any(not value.strip() for value in self.levels.values()):
            raise ValueError("Rubric level descriptions cannot be blank")
        return self


class RubricVersionInput(StrictModel):
    version: Literal[1] = 1
    dimensions: list[RubricDimensionInput] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "RubricVersionInput":
        expected = {
            "problem_clarity",
            "evidence_quality",
            "action_feasibility",
            "validation_design",
        }
        actual = {dimension.dimension_key for dimension in self.dimensions}
        if actual != expected or len(actual) != len(self.dimensions):
            raise ValueError("Rubric V1 must contain each approved dimension exactly once")
        return self


class PublishTaskVersionCommand(RevisionCommand):
    title: str = Field(min_length=3, max_length=180)
    purpose: str = Field(min_length=10, max_length=2_000)
    learner_outcome: str = Field(min_length=10, max_length=2_000)
    instructions: list[str] = Field(min_length=1, max_length=12)
    completion_criteria: list[str] = Field(min_length=1, max_length=12)
    required_deliverables: list[str] = Field(min_length=1, max_length=12)
    content_source_notes: list[str] = Field(min_length=1, max_length=20)
    change_summary: str = Field(min_length=10, max_length=1_000)
    reviewer_calibration_note: str = Field(min_length=10, max_length=1_000)
    allowed_attachment_types: list[AttachmentContentType] = Field(
        default_factory=list, max_length=4
    )
    max_attachment_size_bytes: int = Field(default=0, ge=0, le=5_242_880)
    reference_materials: list[str] = Field(default_factory=list, max_length=20)
    estimated_duration_minutes: int = Field(ge=1, le=480)
    rubric: RubricVersionInput
    reviewer_role: Literal["REVIEWER"] = "REVIEWER"
    feedback_sla_business_days: int = Field(ge=1, le=10)
    sensitivity: Literal["INTERNAL"] = "INTERNAL"
    audience: Literal["LEARNER"] = "LEARNER"
    reviewed_by: UUID

    @model_validator(mode="after")
    def validate_attachment_policy(self) -> "PublishTaskVersionCommand":
        if len(set(self.allowed_attachment_types)) != len(self.allowed_attachment_types):
            raise ValueError("Attachment content types must be unique")
        if bool(self.allowed_attachment_types) != bool(self.max_attachment_size_bytes):
            raise ValueError("Attachment types and size limit must be configured together")
        return self

    @field_validator(
        "instructions",
        "completion_criteria",
        "required_deliverables",
        "content_source_notes",
        "reference_materials",
    )
    @classmethod
    def validate_text_items(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 500 for value in normalized):
            raise ValueError("Task list items must be non-blank and at most 500 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Task list items must be unique")
        return normalized


class InviteOut(StrictModel):
    id: UUID
    purpose: str
    role: Literal["LEARNER"]
    status: str
    expires_at: datetime
    revision: int


class CreateInviteOut(InviteOut):
    invite_token: str
    idempotency_replay: bool = False


class CreateInviteResponse(StrictModel):
    data: CreateInviteOut
    request_id: str


class InviteListOut(StrictModel):
    items: list[InviteOut]


class InviteListResponse(StrictModel):
    data: InviteListOut
    request_id: str


class JoinExchangeCommand(StrictModel):
    token: str = Field(min_length=32, max_length=256)
    return_to: Literal["/app"] = "/app"


class JoinExchangeOut(StrictModel):
    status: Literal["PENDING_IDENTITY"]
    purpose: str
    expires_at: datetime
    csrf_token: str
    safe_entry: Literal["/app"]


class JoinExchangeResponse(StrictModel):
    data: JoinExchangeOut
    request_id: str


class IdentityConfirmCommand(StrictModel):
    display_name: str = Field(min_length=1, max_length=120)
    accepted_purpose: Literal[True]
    return_to: Literal["/app"] = "/app"


class IdentityConfirmOut(StrictModel):
    user_id: UUID
    organization_id: UUID
    roles: list[str]
    enrollment_status: Literal["ACTIVE"]
    safe_entry: Literal["/app"]
    expires_at: datetime
    csrf_token: str


class IdentityConfirmResponse(StrictModel):
    data: IdentityConfirmOut
    request_id: str


class SessionOut(StrictModel):
    user_id: UUID
    organization_id: UUID
    display_name: str
    roles: list[str]
    scope: dict[str, str]
    safe_entry: str
    expires_at: datetime | None
    csrf_required: bool


class SessionResponse(StrictModel):
    data: SessionOut
    request_id: str


class SessionLogoutOut(StrictModel):
    status: Literal["LOGGED_OUT"]


class SessionLogoutResponse(StrictModel):
    data: SessionLogoutOut
    request_id: str


class CurrentActionOut(StrictModel):
    action_type: str
    stage: str
    resource_id: UUID
    title: str
    reason: str
    allowed_commands: list[str]
    revision: int
    responsible_party: str
    feedback_expectation: str


class CurrentActionResponse(StrictModel):
    data: CurrentActionOut
    request_id: str


class AssignmentOut(StrictModel):
    id: UUID
    status: str
    revision: int
    allowed_commands: list[str]
    stable_task_key: str
    task_version: int
    task_title: str
    task_purpose: str
    learner_outcome: str
    instructions: list[str]
    completion_criteria: list[str]
    required_deliverables: list[str]
    allowed_attachment_types: list[str]
    max_attachment_size_bytes: int
    reference_materials: list[str]
    estimated_duration_minutes: int
    feedback_sla_business_days: int
    rubric: dict[str, object]
    submission: "SubmissionOut | None"
    draft: "SubmissionDraftOut | None"
    available_attachments: list["AttachmentOut"]
    latest_revision_feedback: str | None


class AssignmentResponse(StrictModel):
    data: AssignmentOut
    request_id: str


class TaskVersionOut(StrictModel):
    id: UUID
    task_definition_id: UUID
    stable_key: str
    version: int
    title: str
    purpose: str
    learner_outcome: str
    instructions: list[str]
    completion_criteria: list[str]
    required_deliverables: list[str]
    content_source_notes: list[str]
    change_summary: str
    reviewer_calibration_note: str
    allowed_attachment_types: list[str]
    max_attachment_size_bytes: int
    reference_materials: list[str]
    estimated_duration_minutes: int
    rubric: dict[str, object]
    rubric_version: int
    reviewer_role: str
    feedback_sla_business_days: int
    sensitivity: str
    audience: str
    published_by: UUID
    reviewed_by: UUID
    published_at: datetime
    idempotency_replay: bool = False


class TaskVersionResponse(StrictModel):
    data: TaskVersionOut
    request_id: str


class TaskVersionSummaryOut(StrictModel):
    id: UUID
    version: int
    title: str
    published_at: datetime


class TaskDefinitionOut(StrictModel):
    id: UUID
    stable_key: str
    status: str
    revision: int
    content_owner_id: UUID
    versions: list[TaskVersionSummaryOut]
    idempotency_replay: bool = False


class TaskDefinitionResponse(StrictModel):
    data: TaskDefinitionOut
    request_id: str


class TaskDefinitionListOut(StrictModel):
    items: list[TaskDefinitionOut]


class TaskDefinitionListResponse(StrictModel):
    data: TaskDefinitionListOut
    request_id: str


class CommandOut(StrictModel):
    resource_id: UUID
    status: str
    revision: int
    idempotency_replay: bool = False


class CommandResponse(StrictModel):
    data: CommandOut
    request_id: str


class EnrollmentOpsOut(StrictModel):
    id: UUID
    learner_id: UUID
    learner_display_name: str
    reviewer_id: UUID
    reviewer_display_name: str
    status: str
    revision: int
    assignment_statuses: list[str]
    open_review_status: str | None
    allowed_commands: list[str]


class EnrollmentOpsListOut(StrictModel):
    items: list[EnrollmentOpsOut]


class EnrollmentOpsListResponse(StrictModel):
    data: EnrollmentOpsListOut
    request_id: str


class EnrollmentMutationOut(CommandOut):
    reviewer_id: UUID


class EnrollmentMutationResponse(StrictModel):
    data: EnrollmentMutationOut
    request_id: str


class AuditEntryOut(StrictModel):
    id: UUID
    actor_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID | None
    result: str
    request_id: str
    safe_details: dict[str, str | int | bool]
    redacted_fields: list[str]
    occurred_at: datetime


class AuditListOut(StrictModel):
    items: list[AuditEntryOut]


class AuditListResponse(StrictModel):
    data: AuditListOut
    request_id: str


class RuntimeComponentOut(StrictModel):
    status: str
    release: str | None = None
    last_seen_at: datetime | None = None
    stale: bool | None = None


class RuntimeMetricsOut(StrictModel):
    outbox_backlog: int
    notification_dead: int
    permission_denials_24h: int


class RuntimeStatusOut(StrictModel):
    environment: Literal["local", "test", "staging", "production"]
    release: str
    config_schema_version: Literal[1]
    migration_revision: str
    api: RuntimeComponentOut
    database: RuntimeComponentOut
    worker: RuntimeComponentOut
    observability_mode: Literal["LOCAL_STRUCTURED_STDOUT"]
    external_observability_confirmed: Literal[False] = False
    metrics: RuntimeMetricsOut


class RuntimeStatusResponse(StrictModel):
    data: RuntimeStatusOut
    request_id: str


class AttachmentOut(StrictModel):
    id: UUID
    assignment_id: UUID
    purpose: Literal["SUBMISSION_EVIDENCE"]
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    scan_status: str


class PresignedAttachmentOut(AttachmentOut):
    upload_method: Literal["PUT"]
    upload_url: str
    idempotency_replay: bool = False


class PresignedAttachmentResponse(StrictModel):
    data: PresignedAttachmentOut
    request_id: str


class AttachmentResponse(StrictModel):
    data: AttachmentOut
    request_id: str


class SubmissionVersionOut(StrictModel):
    id: UUID
    version_no: int
    body: str
    created_at: datetime
    attachments: list[AttachmentOut]
    review_id: UUID | None
    review_status: str | None
    decision: str | None
    feedback: str | None


class SubmissionOut(StrictModel):
    id: UUID
    assignment_id: UUID
    current_version_no: int
    versions: list[SubmissionVersionOut]


class SubmissionDraftOut(StrictModel):
    body: str
    attachment_ids: list[UUID]
    revision: int
    updated_at: datetime
    idempotency_replay: bool = False


class SubmissionHistoryResponse(StrictModel):
    data: SubmissionOut
    request_id: str


class SubmissionMutationOut(StrictModel):
    assignment_id: UUID
    assignment_status: str
    assignment_revision: int
    submission_id: UUID
    submission_version_id: UUID
    version_no: int
    attachment_ids: list[UUID]
    idempotency_replay: bool = False


class SubmissionMutationResponse(StrictModel):
    data: SubmissionMutationOut
    request_id: str


class SubmissionDraftResponse(StrictModel):
    data: SubmissionDraftOut
    request_id: str


class ReviewQueueItemOut(StrictModel):
    id: UUID
    assignment_id: UUID
    submission_id: UUID
    submission_version_id: UUID
    status: str
    revision: int
    allowed_commands: list[str]
    learner_name: str
    task_title: str
    task_version: int
    submission_version_no: int
    assigned_at: datetime
    started_at: datetime | None
    priority_reason: str
    material_status: Literal["COMPLETE", "INCOMPLETE"]


class ReviewQueueOut(StrictModel):
    items: list[ReviewQueueItemOut]


class ReviewQueueResponse(StrictModel):
    data: ReviewQueueOut
    request_id: str


class ReviewAttachmentOut(StrictModel):
    id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    status: str
    scan_status: str
    download_path: str


class ReviewMaterialOut(StrictModel):
    status: Literal["COMPLETE", "INCOMPLETE"]
    missing_items: list[str]
    required_deliverables: list[str]
    attachments: list[ReviewAttachmentOut]


class RubricEvaluationOut(StrictModel):
    dimension_key: str
    rating: str
    feedback: str | None


class EvaluationOut(StrictModel):
    id: UUID
    decision: str
    overall_decision: Literal["APPROVE", "REQUEST_REVISION"]
    overall_feedback: str
    rubric_evaluations: list[RubricEvaluationOut]
    feedback_structure_version: int
    reviewer_id: UUID
    review_revision: int
    created_at: datetime


class ReviewDetailOut(ReviewQueueItemOut):
    submission_body: str
    task_purpose: str
    completion_criteria: list[str]
    required_deliverables: list[str]
    rubric: dict[str, object]
    materials: ReviewMaterialOut
    finalized_at: datetime | None
    evaluation: EvaluationOut | None


class ReviewDetailResponse(StrictModel):
    data: ReviewDetailOut
    request_id: str


class ReviewMutationOut(StrictModel):
    review_id: UUID
    review_status: str
    review_revision: int
    assignment_id: UUID
    assignment_status: str
    assignment_revision: int
    evaluation_id: UUID | None = None
    decision: str | None = None
    idempotency_replay: bool = False


class ReviewMutationResponse(StrictModel):
    data: ReviewMutationOut
    request_id: str


class ResultRubricFeedbackOut(StrictModel):
    dimension_key: str
    title: str
    rating: str
    feedback: str | None


class ResultEvaluationOut(StrictModel):
    id: UUID
    reviewer_id: UUID
    decision: Literal["PASS"]
    overall_feedback: str
    rubric_feedback: list[ResultRubricFeedbackOut]
    created_at: datetime


class HandoffOut(StrictModel):
    id: UUID
    status: Literal["READY"]
    owner_user_id: UUID
    owner_display_name: str
    title: str
    next_step_code: Literal["CONFIRM_HANDOFF"]
    next_step_title: str
    instructions: str
    created_at: datetime


class NotificationDeliveryOut(StrictModel):
    status: str
    channel: str | None
    display_status: str
    attempt_count: int
    next_attempt_at: datetime | None
    last_error_code: str | None
    delivered_at: datetime | None
    delivery_scope: Literal["LOCAL_TEST_ONLY"] = "LOCAL_TEST_ONLY"
    external_delivery_confirmed: Literal[False] = False


class AiSummaryOut(StrictModel):
    status: Literal["NOT_ENABLED"] = "NOT_ENABLED"
    message: str


class ResultOut(StrictModel):
    outcome_id: UUID
    decision: Literal["PASS"]
    status: str
    summary: str
    evaluation: ResultEvaluationOut
    handoff: HandoffOut
    notification: NotificationDeliveryOut
    ai_summary: AiSummaryOut
    created_at: datetime


class ResultResponse(StrictModel):
    data: ResultOut
    request_id: str


class TimelineItemOut(StrictModel):
    item_id: str
    event_type: str
    title: str
    occurred_at: datetime
    object_type: str
    object_id: UUID
    details: dict[str, str | int | bool | None]


class TimelineOut(StrictModel):
    items: list[TimelineItemOut]
    next_cursor: str | None


class TimelineResponse(StrictModel):
    data: TimelineOut
    request_id: str


class HealthOut(StrictModel):
    status: Literal["ok"]
    release: str


class ErrorDetail(StrictModel):
    code: str
    message: str
    details: dict[str, object]
    retryable: bool


class ErrorResponse(StrictModel):
    error: ErrorDetail
    request_id: str
