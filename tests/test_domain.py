import uuid

import pytest

from journey_api.domain import AssignmentActionState, resolve_current_action
from journey_api.models import AssignmentStatus, EnrollmentStatus


FALLBACK_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")


def state(status: AssignmentStatus, *, position: int = 1) -> AssignmentActionState:
    return AssignmentActionState(uuid.uuid4(), status, 3, position)


@pytest.mark.parametrize(
    ("status", "action_type", "commands"),
    [
        (AssignmentStatus.AVAILABLE, "START_OR_CONTINUE_TASK", ("start",)),
        (AssignmentStatus.IN_PROGRESS, "START_OR_CONTINUE_TASK", ("submit",)),
        (AssignmentStatus.SUBMITTED, "WAIT_FOR_REVIEW", ()),
        (AssignmentStatus.IN_REVIEW, "WAIT_FOR_REVIEW", ()),
        (AssignmentStatus.NEEDS_REVISION, "REVISE_SUBMISSION", ("submit_revision",)),
        (AssignmentStatus.COMPLETED, "VIEW_RESULT_OR_HANDOFF", ()),
    ],
)
def test_current_action_is_server_authoritative(status, action_type, commands):
    selected = state(status)
    action = resolve_current_action(
        fallback_resource_id=FALLBACK_ID,
        fallback_revision=1,
        enrollment_status=EnrollmentStatus.ACTIVE,
        assignments=(selected,),
    )
    assert action.action_type == action_type
    assert action.resource_id == selected.id
    assert action.revision == selected.revision
    assert action.allowed_commands == commands


@pytest.mark.parametrize(
    ("enrollment_status", "action_type", "commands"),
    [
        (None, "RESOLVE_ENROLLMENT", ()),
        (EnrollmentStatus.PENDING_IDENTITY, "CONFIRM_IDENTITY", ("confirm_identity",)),
        (EnrollmentStatus.CANCELLED, "RESOLVE_ENROLLMENT", ()),
    ],
)
def test_current_action_handles_enrollment_boundaries(
    enrollment_status, action_type, commands
):
    action = resolve_current_action(
        fallback_resource_id=FALLBACK_ID,
        fallback_revision=4,
        enrollment_status=enrollment_status,
        assignments=(),
    )
    assert action.action_type == action_type
    assert action.resource_id == FALLBACK_ID
    assert action.revision == 4
    assert action.allowed_commands == commands


def test_current_action_uses_business_priority_then_assignment_order():
    waiting = state(AssignmentStatus.SUBMITTED, position=1)
    available = state(AssignmentStatus.AVAILABLE, position=2)
    revision = state(AssignmentStatus.NEEDS_REVISION, position=3)
    action = resolve_current_action(
        fallback_resource_id=FALLBACK_ID,
        fallback_revision=1,
        enrollment_status=EnrollmentStatus.ACTIVE,
        assignments=(waiting, available, revision),
    )
    assert action.action_type == "REVISE_SUBMISSION"
    assert action.resource_id == revision.id


def test_current_action_moves_to_next_available_task_after_completion():
    completed = state(AssignmentStatus.COMPLETED, position=1)
    next_task = state(AssignmentStatus.AVAILABLE, position=2)
    action = resolve_current_action(
        fallback_resource_id=FALLBACK_ID,
        fallback_revision=1,
        enrollment_status=EnrollmentStatus.ACTIVE,
        assignments=(completed, next_task),
    )
    assert action.action_type == "START_OR_CONTINUE_TASK"
    assert action.resource_id == next_task.id


def test_active_enrollment_without_task_requires_safe_resolution():
    action = resolve_current_action(
        fallback_resource_id=FALLBACK_ID,
        fallback_revision=2,
        enrollment_status=EnrollmentStatus.ACTIVE,
        assignments=(state(AssignmentStatus.CANCELLED),),
    )
    assert action.action_type == "RESOLVE_ENROLLMENT"
    assert action.allowed_commands == ()
