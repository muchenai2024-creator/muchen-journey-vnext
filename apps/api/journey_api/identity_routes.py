import uuid
from datetime import timedelta
from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.idempotency import canonical_hash, find_replay, store_result
from journey_api.identity import (
    CSRF_COOKIE,
    JOIN_COOKIE,
    add_audit,
    clear_session_cookies,
    credential_hash,
    derive_invite_token,
    enforce_invite_exchange_limit,
    random_token,
    set_join_cookies,
    set_session_cookies,
    utc_now,
)
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Enrollment,
    EnrollmentStatus,
    ExternalIdentity,
    IdentitySession,
    Invite,
    InviteStatus,
    JoinContext,
    JoinContextStatus,
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
    CommandOut,
    CommandResponse,
    CreateInviteCommand,
    CreateInviteOut,
    CreateInviteResponse,
    IdentityConfirmCommand,
    IdentityConfirmOut,
    IdentityConfirmResponse,
    InviteListOut,
    InviteListResponse,
    InviteOut,
    JoinExchangeCommand,
    JoinExchangeOut,
    JoinExchangeResponse,
    RevokeInviteCommand,
    SessionLogoutOut,
    SessionLogoutResponse,
    SessionOut,
    SessionResponse,
)

router = APIRouter(prefix="/api/v1")


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


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


def ensure_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "状态已更新，请确认最新内容后重试。",
            details={"current_revision": actual},
        )


def visible_invite_status(invite: Invite) -> str:
    if invite.status == InviteStatus.ACTIVE and invite.expires_at <= utc_now():
        return InviteStatus.EXPIRED.value
    return invite.status.value


def deny_exchange(
    session: Session,
    request: Request,
    *,
    invite: Invite | None,
    message: str,
    code: str = "INVITE_EXPIRED_OR_REVOKED",
    status_code: int = 410,
) -> None:
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=invite.organization_id if invite else None,
        action="invite.exchange_denied",
        resource_type="invite",
        resource_id=invite.id if invite else None,
        result="DENIED",
        details={"reason": code},
    )
    session.commit()
    raise ApiError(status_code, code, message)


@router.post("/ops/invites", response_model=CreateInviteResponse)
def create_invite(
    command: CreateInviteCommand,
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
        command="invite.create",
        key=idempotency_key,
        payload=payload,
    )
    settings = get_settings()
    request_hash = canonical_hash(payload)
    invite_token = derive_invite_token(
        secret=settings.invite_secret,
        actor_id=actor.id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return envelope(request, CreateInviteOut(**replay, invite_token=invite_token))

    reviewer = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == command.reviewer_id,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.REVIEWER,
        )
    )
    task = session.scalar(
        select(TaskVersion)
        .join(TaskDefinition, TaskDefinition.id == TaskVersion.task_definition_id)
        .where(
            TaskVersion.id == command.task_version_id,
            TaskVersion.organization_id == actor.organization_id,
            TaskDefinition.organization_id == actor.organization_id,
            TaskDefinition.status == TaskDefinitionStatus.PUBLISHED,
        )
    )
    if reviewer is None or task is None:
        raise ApiError(422, "VALIDATION_FAILED", "邀请的主管或任务版本无效。")
    if command.target_user_id is not None:
        target = session.scalar(
            select(User).where(
                User.id == command.target_user_id,
                User.organization_id == actor.organization_id,
            )
        )
        if target is None:
            raise ApiError(422, "VALIDATION_FAILED", "邀请目标身份无效。")

    now = utc_now()
    invite = Invite(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        token_hash=credential_hash(settings.invite_secret, "invite", invite_token),
        purpose=command.purpose.strip(),
        role=Role.LEARNER,
        reviewer_id=command.reviewer_id,
        task_version_id=command.task_version_id,
        target_user_id=command.target_user_id,
        status=InviteStatus.ACTIVE,
        expires_at=now + timedelta(hours=command.expires_in_hours),
        created_by=actor.id,
        revision=1,
    )
    session.add(invite)
    result = {
        "id": str(invite.id),
        "purpose": invite.purpose,
        "role": invite.role.value,
        "status": invite.status.value,
        "expires_at": invite.expires_at.isoformat(),
        "revision": invite.revision,
    }
    store_result(
        session,
        actor_id=actor.id,
        command="invite.create",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_event(session, "invite.created.v1", "invite", invite.id)
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="invite.created",
        resource_type="invite",
        resource_id=invite.id,
        result="SUCCESS",
        details={"role": invite.role.value},
    )
    session.commit()
    return envelope(request, CreateInviteOut(**result, invite_token=invite_token))


@router.get("/ops/invites", response_model=InviteListResponse)
def list_invites(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    invites = session.scalars(
        select(Invite)
        .where(Invite.organization_id == actor.organization_id)
        .order_by(Invite.created_at.desc())
        .limit(100)
    ).all()
    return envelope(
        request,
        InviteListOut(
            items=[
                InviteOut(
                    id=invite.id,
                    purpose=invite.purpose,
                    role="LEARNER",
                    status=visible_invite_status(invite),
                    expires_at=invite.expires_at,
                    revision=invite.revision,
                )
                for invite in invites
            ]
        ),
    )


@router.post("/ops/invites/{invite_id}/revoke", response_model=CommandResponse)
def revoke_invite(
    invite_id: uuid.UUID,
    command: RevokeInviteCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="invite.revoke",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, CommandOut(**replay))
    invite = session.scalar(
        select(Invite)
        .where(Invite.id == invite_id, Invite.organization_id == actor.organization_id)
        .with_for_update()
    )
    if invite is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的邀请。")
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="invite.revoke",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, CommandOut(**replay))
    ensure_revision(invite.revision, command.expected_revision)
    if invite.status != InviteStatus.ACTIVE:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前邀请不能撤销。")
    now = utc_now()
    if invite.expires_at <= now:
        invite.status = InviteStatus.EXPIRED
        invite.revision += 1
        session.commit()
        raise ApiError(410, "INVITE_EXPIRED_OR_REVOKED", "邀请已过期。")

    context = session.scalar(
        select(JoinContext).where(JoinContext.invite_id == invite.id).with_for_update()
    )
    if context is not None and context.status == JoinContextStatus.PENDING:
        context.status = JoinContextStatus.REVOKED
        enrollment = session.get(Enrollment, context.enrollment_id)
        if enrollment is not None and enrollment.status == EnrollmentStatus.PENDING_IDENTITY:
            enrollment.status = EnrollmentStatus.CANCELLED
            enrollment.revision += 1
        user = session.get(User, context.user_id)
        if context.created_user and user is not None and user.status == UserStatus.PENDING_IDENTITY:
            user.status = UserStatus.DISABLED

    invite.status = InviteStatus.REVOKED
    invite.revoked_at = now
    invite.revoke_reason = command.reason.strip()
    invite.revision += 1
    result = {
        "resource_id": str(invite.id),
        "status": invite.status.value,
        "revision": invite.revision,
    }
    store_result(
        session,
        actor_id=actor.id,
        command="invite.revoke",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_event(session, "invite.revoked.v1", "invite", invite.id)
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="invite.revoked",
        resource_type="invite",
        resource_id=invite.id,
        result="SUCCESS",
        details={"reason": invite.revoke_reason},
    )
    session.commit()
    return envelope(request, CommandOut(**result))


@router.post("/join/exchange", response_model=JoinExchangeResponse)
def exchange_invite(
    command: JoinExchangeCommand,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    enforce_invite_exchange_limit(request)
    settings = get_settings()
    token_hash = credential_hash(settings.invite_secret, "invite", command.token)
    invite = session.scalar(select(Invite).where(Invite.token_hash == token_hash).with_for_update())
    if invite is None:
        deny_exchange(session, request, invite=None, message="邀请无效，请联系运营重新获取。")
    assert invite is not None
    now = utc_now()
    if invite.status != InviteStatus.ACTIVE:
        deny_exchange(session, request, invite=invite, message="邀请已失效，请联系运营重新获取。")
    if invite.expires_at <= now:
        invite.status = InviteStatus.EXPIRED
        invite.revision += 1
        deny_exchange(session, request, invite=invite, message="邀请已过期，请联系运营重新获取。")
    existing_context = session.scalar(
        select(JoinContext).where(JoinContext.invite_id == invite.id).with_for_update()
    )
    if existing_context is not None:
        deny_exchange(session, request, invite=invite, message="邀请已经交换，不能再次使用。")

    created_user = invite.target_user_id is None
    if created_user:
        user = User(
            id=uuid.uuid4(),
            organization_id=invite.organization_id,
            display_name="待确认身份",
            status=UserStatus.PENDING_IDENTITY,
        )
        session.add(user)
        session.flush()
    else:
        user = session.get(User, invite.target_user_id)
        if user is None or user.organization_id != invite.organization_id:
            deny_exchange(session, request, invite=invite, message="邀请目标身份无效。")
        if user.status != UserStatus.ACTIVE:
            deny_exchange(
                session,
                request,
                invite=invite,
                message="目标身份已停用，请联系运营处理。",
                code="FORBIDDEN",
                status_code=403,
            )
        active_enrollment = session.scalar(
            select(Enrollment.id).where(
                Enrollment.organization_id == invite.organization_id,
                Enrollment.learner_id == user.id,
                Enrollment.status.in_(
                    [EnrollmentStatus.PENDING_IDENTITY, EnrollmentStatus.ACTIVE]
                ),
            )
        )
        if active_enrollment is not None:
            deny_exchange(
                session,
                request,
                invite=invite,
                message="该身份已有进行中的 Enrollment。",
                code="INVALID_STATE_TRANSITION",
                status_code=409,
            )

    enrollment = Enrollment(
        id=uuid.uuid4(),
        organization_id=invite.organization_id,
        learner_id=user.id,
        reviewer_id=invite.reviewer_id,
        status=EnrollmentStatus.PENDING_IDENTITY,
        revision=1,
    )
    join_token = random_token()
    csrf_token = random_token()
    expires_at = min(
        invite.expires_at,
        now + timedelta(minutes=settings.join_context_ttl_minutes),
    )
    context = JoinContext(
        id=uuid.uuid4(),
        invite_id=invite.id,
        user_id=user.id,
        enrollment_id=enrollment.id,
        token_hash=credential_hash(settings.session_secret, "join", join_token),
        csrf_token_hash=credential_hash(settings.session_secret, "join-csrf", csrf_token),
        status=JoinContextStatus.PENDING,
        created_user=created_user,
        expires_at=expires_at,
    )
    session.add_all([enrollment, context])
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=invite.organization_id,
        action="invite.exchanged",
        resource_type="invite",
        resource_id=invite.id,
        result="SUCCESS",
        details={},
    )
    session.commit()
    max_age = max(1, int((expires_at - now).total_seconds()))
    set_join_cookies(response, join_token, csrf_token, max_age)
    return envelope(
        request,
        JoinExchangeOut(
            status="PENDING_IDENTITY",
            purpose=invite.purpose,
            expires_at=expires_at,
            csrf_token=csrf_token,
            safe_entry="/app",
        ),
    )


@router.post("/identity/confirm", response_model=IdentityConfirmResponse)
def confirm_identity(
    command: IdentityConfirmCommand,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    join_token = request.cookies.get(JOIN_COOKIE, "")
    csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
    csrf_header = request.headers.get("X-CSRF-Token", "")
    if not join_token:
        raise ApiError(401, "UNAUTHENTICATED", "加入上下文不存在或已过期。")
    if not csrf_cookie or not csrf_header or not compare_digest(csrf_cookie, csrf_header):
        raise ApiError(403, "FORBIDDEN", "安全校验失败，请重新打开邀请。")
    context = session.scalar(
        select(JoinContext)
        .where(
            JoinContext.token_hash
            == credential_hash(settings.session_secret, "join", join_token)
        )
        .with_for_update()
    )
    expected_csrf = credential_hash(settings.session_secret, "join-csrf", csrf_header)
    if context is None or not compare_digest(context.csrf_token_hash, expected_csrf):
        raise ApiError(401, "UNAUTHENTICATED", "加入上下文不存在或已过期。")
    now = utc_now()
    if context.status != JoinContextStatus.PENDING or context.expires_at <= now:
        raise ApiError(410, "INVITE_EXPIRED_OR_REVOKED", "加入上下文已失效，请联系运营。")
    invite = session.scalar(select(Invite).where(Invite.id == context.invite_id).with_for_update())
    enrollment = session.scalar(
        select(Enrollment).where(Enrollment.id == context.enrollment_id).with_for_update()
    )
    user = session.scalar(select(User).where(User.id == context.user_id).with_for_update())
    if (
        invite is None
        or enrollment is None
        or user is None
        or invite.status != InviteStatus.ACTIVE
        or invite.expires_at <= now
        or enrollment.status != EnrollmentStatus.PENDING_IDENTITY
        or user.status not in {UserStatus.PENDING_IDENTITY, UserStatus.ACTIVE}
    ):
        raise ApiError(410, "INVITE_EXPIRED_OR_REVOKED", "邀请已失效，请联系运营。")

    if context.created_user:
        user.display_name = command.display_name.strip()
        user.status = UserStatus.ACTIVE
    role_assignment = session.scalar(
        select(RoleAssignment).where(
            RoleAssignment.user_id == user.id,
            RoleAssignment.role == Role.LEARNER,
        )
    )
    if role_assignment is None:
        session.add(
            RoleAssignment(
                id=uuid.uuid4(),
                organization_id=invite.organization_id,
                user_id=user.id,
                role=Role.LEARNER,
            )
        )
    session.add(
        ExternalIdentity(
            id=uuid.uuid4(),
            organization_id=invite.organization_id,
            user_id=user.id,
            provider="INVITE",
            subject=str(invite.id),
        )
    )
    enrollment.status = EnrollmentStatus.ACTIVE
    enrollment.revision += 1
    task_version = session.scalar(
        select(TaskVersion)
        .join(TaskDefinition, TaskDefinition.id == TaskVersion.task_definition_id)
        .where(
            TaskVersion.id == invite.task_version_id,
            TaskVersion.organization_id == invite.organization_id,
            TaskDefinition.organization_id == invite.organization_id,
            TaskDefinition.status == TaskDefinitionStatus.PUBLISHED,
        )
    )
    if task_version is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "邀请引用的任务版本已不可用于新 Assignment。")
    assignment = Assignment(
        id=uuid.uuid4(),
        organization_id=invite.organization_id,
        enrollment_id=enrollment.id,
        task_definition_id=task_version.task_definition_id,
        task_version_id=invite.task_version_id,
        position=1,
        status=AssignmentStatus.AVAILABLE,
        revision=1,
    )
    session.add(assignment)
    invite.status = InviteStatus.CONSUMED
    invite.consumed_by = user.id
    invite.consumed_at = now
    invite.revision += 1
    context.status = JoinContextStatus.CONFIRMED
    context.confirmed_at = now

    session_token = random_token()
    session_csrf_token = random_token()
    expires_at = now + timedelta(hours=settings.session_ttl_hours)
    identity_session = IdentitySession(
        id=uuid.uuid4(),
        organization_id=invite.organization_id,
        user_id=user.id,
        role=Role.LEARNER,
        token_hash=credential_hash(settings.session_secret, "session", session_token),
        csrf_token_hash=credential_hash(settings.session_secret, "csrf", session_csrf_token),
        expires_at=expires_at,
    )
    session.add(identity_session)
    add_event(session, "invite.consumed.v1", "invite", invite.id)
    add_event(session, "identity.confirmed.v1", "user", user.id)
    add_event(session, "enrollment.activated.v1", "enrollment", enrollment.id)
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=invite.organization_id,
        actor_id=user.id,
        action="identity.confirmed",
        resource_type="user",
        resource_id=user.id,
        result="SUCCESS",
        details={"provider": "INVITE"},
    )
    session.commit()
    set_session_cookies(
        response,
        session_token,
        session_csrf_token,
        max_age=settings.session_ttl_hours * 3600,
    )
    return envelope(
        request,
        IdentityConfirmOut(
            user_id=user.id,
            organization_id=user.organization_id,
            roles=[Role.LEARNER.value],
            enrollment_status="ACTIVE",
            safe_entry="/app",
            expires_at=expires_at,
            csrf_token=session_csrf_token,
        ),
    )


@router.get("/session", response_model=SessionResponse)
def current_session(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    roles = session.scalars(
        select(RoleAssignment.role).where(
            RoleAssignment.user_id == actor.id,
            RoleAssignment.organization_id == actor.organization_id,
        )
    ).all()
    expires_at = None
    if actor.session_id is not None:
        identity_session = session.get(IdentitySession, actor.session_id)
        expires_at = identity_session.expires_at if identity_session else None
    safe_entry = {
        Role.LEARNER: "/app",
        Role.REVIEWER: "/review",
        Role.OPERATOR: "/ops/invites",
    }[actor.role]
    return envelope(
        request,
        SessionOut(
            user_id=actor.id,
            organization_id=actor.organization_id,
            display_name=actor.display_name,
            roles=sorted(role.value for role in roles),
            scope={"organization_id": str(actor.organization_id)},
            safe_entry=safe_entry,
            expires_at=expires_at,
            csrf_required=actor.session_id is not None,
        ),
    )


@router.post("/session/logout", response_model=SessionLogoutResponse)
def logout_session(
    request: Request,
    response: Response,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    if actor.session_id is None:
        raise ApiError(400, "INVALID_REQUEST", "fixture 身份没有可撤销的 vNext 会话。")
    identity_session = session.scalar(
        select(IdentitySession)
        .where(IdentitySession.id == actor.session_id)
        .with_for_update()
    )
    if identity_session is None or identity_session.revoked_at is not None:
        raise ApiError(401, "UNAUTHENTICATED", "vNext 会话无效或已退出。")
    identity_session.revoked_at = utc_now()
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="session.logged_out",
        resource_type="identity_session",
        resource_id=identity_session.id,
        result="SUCCESS",
        details={},
    )
    session.commit()
    clear_session_cookies(response)
    return envelope(request, SessionLogoutOut(status="LOGGED_OUT"))
