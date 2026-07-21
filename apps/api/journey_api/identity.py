import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy.dialects.postgresql import insert

from journey_api.config import Settings, get_settings
from journey_api.db import SessionLocal
from journey_api.errors import ApiError
from journey_api.models import AuditEntry, AuthRateLimit

SESSION_COOKIE = "journey_next_session"
JOIN_COOKIE = "journey_next_join"
CSRF_COOKIE = "journey_next_csrf"


def utc_now() -> datetime:
    return datetime.now(UTC)


def random_token() -> str:
    return secrets.token_urlsafe(32)


def credential_hash(secret: str, purpose: str, value: str) -> str:
    return hmac.new(secret.encode(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def derive_invite_token(
    *, secret: str, actor_id: uuid.UUID, idempotency_key: str, request_hash: str
) -> str:
    material = f"invite-create-v1:{actor_id}:{idempotency_key}:{request_hash}".encode()
    digest = hmac.new(secret.encode(), material, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def cookie_secure(settings: Settings | None = None) -> bool:
    current = settings or get_settings()
    return current.app_env in {"staging", "production"}


def set_join_cookies(response: Response, join_token: str, csrf_token: str, max_age: int) -> None:
    secure = cookie_secure()
    response.set_cookie(
        JOIN_COOKIE,
        join_token,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=False,
        samesite="lax",
    )


def set_session_cookies(response: Response, session_token: str, csrf_token: str, max_age: int) -> None:
    secure = cookie_secure()
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=False,
        samesite="lax",
    )
    response.delete_cookie(JOIN_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")


def clear_session_cookies(response: Response) -> None:
    secure = cookie_secure()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, httponly=False, samesite="lax")


def add_audit(
    session,
    *,
    request_id: str,
    action: str,
    resource_type: str,
    result: str,
    organization_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    resource_id: uuid.UUID | None = None,
    details: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            request_id=request_id,
            details=details or {},
        )
    )


def enforce_invite_exchange_limit(request: Request) -> None:
    settings = get_settings()
    now = utc_now()
    window_started = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    client_host = request.client.host if request.client else "unknown"
    subject_hash = credential_hash(settings.invite_secret, "rate-limit-client", client_host)
    statement = (
        insert(AuthRateLimit)
        .values(
            id=uuid.uuid4(),
            scope="invite.exchange",
            subject_hash=subject_hash,
            window_started_at=window_started,
            attempts=1,
        )
        .on_conflict_do_update(
            constraint="uq_auth_rate_limit_window",
            set_={"attempts": AuthRateLimit.attempts + 1},
        )
        .returning(AuthRateLimit.attempts)
    )
    with SessionLocal.begin() as rate_session:
        attempts = rate_session.scalar(statement)
    if attempts is not None and attempts > settings.invite_exchange_limit:
        retry_after = int((window_started + timedelta(minutes=5) - now).total_seconds()) + 1
        raise ApiError(
            429,
            "RATE_LIMITED",
            "邀请验证尝试过多，请稍后再试。",
            details={"retry_after_seconds": max(1, retry_after)},
            retryable=True,
        )
