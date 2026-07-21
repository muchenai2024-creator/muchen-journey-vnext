from dataclasses import dataclass
from uuid import UUID

from journey_api.models import AssignmentStatus, EnrollmentStatus


@dataclass(frozen=True)
class AssignmentActionState:
    id: UUID
    status: AssignmentStatus
    revision: int
    position: int


@dataclass(frozen=True)
class CurrentAction:
    action_type: str
    stage: str
    resource_id: UUID
    revision: int
    title: str
    reason: str
    allowed_commands: tuple[str, ...]


def assignment_action(
    status: AssignmentStatus,
) -> tuple[str, str, str, str, tuple[str, ...]]:
    actions = {
        AssignmentStatus.AVAILABLE: (
            "START_OR_CONTINUE_TASK",
            "当前任务",
            "开始当前任务",
            "任务已经准备好，现在可以开始。",
            ("start",),
        ),
        AssignmentStatus.IN_PROGRESS: (
            "START_OR_CONTINUE_TASK",
            "当前任务",
            "继续完成当前任务",
            "草稿仍在进行中，完成后提交给主管。",
            ("submit",),
        ),
        AssignmentStatus.SUBMITTED: (
            "WAIT_FOR_REVIEW",
            "等待反馈",
            "等待主管开始评审",
            "提交已经保存，主管将在两个工作日内反馈。",
            (),
        ),
        AssignmentStatus.IN_REVIEW: (
            "WAIT_FOR_REVIEW",
            "等待反馈",
            "主管正在评审",
            "主管已经开始处理这份固定版本。",
            (),
        ),
        AssignmentStatus.NEEDS_REVISION: (
            "REVISE_SUBMISSION",
            "需要修订",
            "根据反馈修订任务",
            "当前版本需要补充后再次提交。",
            ("submit_revision",),
        ),
        AssignmentStatus.COMPLETED: (
            "VIEW_RESULT_OR_HANDOFF",
            "本阶段已通过",
            "查看结果与交接",
            "当前探索营任务已经通过。",
            (),
        ),
    }
    return actions[status]


def resolve_current_action(
    *,
    fallback_resource_id: UUID,
    fallback_revision: int,
    enrollment_status: EnrollmentStatus | None,
    assignments: tuple[AssignmentActionState, ...],
) -> CurrentAction:
    if enrollment_status is None:
        return CurrentAction(
            "RESOLVE_ENROLLMENT",
            "加入待处理",
            fallback_resource_id,
            fallback_revision,
            "联系运营确认加入状态",
            "当前身份没有有效的探索营 Enrollment。",
            (),
        )
    if enrollment_status == EnrollmentStatus.PENDING_IDENTITY:
        return CurrentAction(
            "CONFIRM_IDENTITY",
            "待确认身份",
            fallback_resource_id,
            fallback_revision,
            "确认身份后开始",
            "完成最小身份确认后才能查看当前任务。",
            ("confirm_identity",),
        )
    if enrollment_status == EnrollmentStatus.CANCELLED:
        return CurrentAction(
            "RESOLVE_ENROLLMENT",
            "加入已停止",
            fallback_resource_id,
            fallback_revision,
            "联系运营确认恢复方式",
            "当前 Enrollment 已取消，系统不会显示或创建任务写入动作。",
            (),
        )

    active = tuple(item for item in assignments if item.status != AssignmentStatus.CANCELLED)
    if enrollment_status == EnrollmentStatus.ACTIVE:
        priorities = (
            (AssignmentStatus.NEEDS_REVISION,),
            (AssignmentStatus.AVAILABLE, AssignmentStatus.IN_PROGRESS),
            (AssignmentStatus.SUBMITTED, AssignmentStatus.IN_REVIEW),
        )
        for statuses in priorities:
            matching = sorted(
                (item for item in active if item.status in statuses),
                key=lambda item: (item.position, str(item.id)),
            )
            if matching:
                selected = matching[0]
                action_type, stage, title, reason, commands = assignment_action(selected.status)
                return CurrentAction(
                    action_type,
                    stage,
                    selected.id,
                    selected.revision,
                    title,
                    reason,
                    commands,
                )

    completed = sorted(
        (item for item in active if item.status == AssignmentStatus.COMPLETED),
        key=lambda item: (item.position, str(item.id)),
    )
    if completed:
        selected = completed[-1]
        action_type, stage, title, reason, commands = assignment_action(selected.status)
        return CurrentAction(
            action_type,
            stage,
            selected.id,
            selected.revision,
            title,
            reason,
            commands,
        )
    return CurrentAction(
        "RESOLVE_ENROLLMENT",
        "任务待配置",
        fallback_resource_id,
        fallback_revision,
        "联系运营确认当前任务",
        "Enrollment 已生效，但还没有可执行的已发布任务。",
        (),
    )
