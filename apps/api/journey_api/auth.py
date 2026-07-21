from dataclasses import dataclass
from uuid import UUID

from datetime import UTC, datetime
from hmac import compare_digest

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.identity import CSRF_COOKIE, SESSION_COOKIE, credential_hash
from journey_api.models import IdentitySession, Role, RoleAssignment, User, UserStatus


@dataclass(frozen=True)
class Actor:
    id: UUID
    organization_id: UUID
    role: Role
    display_name: str
    session_id: UUID | None = None


def get_actor(
    request: Request,
    x_fixture_role: str | None = Header(default=None, alias="X-Fixture-Role"),
    session: Session = Depends(get_db),
) -> Actor:
    settings = get_settings()
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        token_hash = credential_hash(settings.session_secret, "session", session_token)
        row = session.execute(
            select(IdentitySession, User, RoleAssignment)
            .join(User, User.id == IdentitySession.user_id)
            .join(
                RoleAssignment,
                (RoleAssignment.user_id == IdentitySession.user_id)
                & (RoleAssignment.role == IdentitySession.role),
            )
            .where(
                IdentitySession.token_hash == token_hash,
                IdentitySession.revoked_at.is_(None),
                IdentitySession.expires_at > datetime.now(UTC),
                User.status == UserStatus.ACTIVE,
                User.organization_id == IdentitySession.organization_id,
                RoleAssignment.organization_id == IdentitySession.organization_id,
            )
        ).first()
        if row is None:
            raise ApiError(401, "UNAUTHENTICATED", "vNext 会话无效或已过期。")
        identity_session, user, assignment = row
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
            csrf_header = request.headers.get("X-CSRF-Token", "")
            expected_hash = credential_hash(settings.session_secret, "csrf", csrf_header)
            if (
                not csrf_cookie
                or not csrf_header
                or not compare_digest(csrf_cookie, csrf_header)
                or not compare_digest(identity_session.csrf_token_hash, expected_hash)
            ):
                raise ApiError(403, "FORBIDDEN", "安全校验失败，请刷新后重试。")
        return Actor(
            user.id,
            user.organization_id,
            assignment.role,
            user.display_name,
            identity_session.id,
        )
    if not settings.allow_fixture_identity or settings.app_env not in {"local", "test"}:
        raise ApiError(401, "UNAUTHENTICATED", "需要有效的 vNext 会话。")
    try:
        requested_role = Role((x_fixture_role or "").upper())
    except ValueError as exc:
        raise ApiError(401, "UNAUTHENTICATED", "本地 fixture 身份无效。") from exc
    row = session.execute(
        select(User, RoleAssignment)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(RoleAssignment.role == requested_role, User.status == UserStatus.ACTIVE)
    ).first()
    if row is None:
        raise ApiError(401, "UNAUTHENTICATED", "本地 fixture 身份不存在。")
    user, assignment = row
    return Actor(user.id, user.organization_id, assignment.role, user.display_name, None)


def require_role(actor: Actor, role: Role) -> None:
    if actor.role != role:
        raise ApiError(403, "FORBIDDEN", "当前身份无权执行此操作。")
