import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID, REVIEWER_ID, TASK_VERSION_ID
from journey_api.identity import SESSION_COOKIE, utc_now
from journey_api.main import app
from journey_api.models import (
    AuditEntry,
    Enrollment,
    EnrollmentStatus,
    ExternalIdentity,
    IdentitySession,
    Invite,
    InviteStatus,
    JoinContext,
    OutboxEvent,
    Role,
    RoleAssignment,
    User,
    UserStatus,
)

operator_headers = {"X-Fixture-Role": "OPERATOR"}


def client_for(label: str) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=(label, 50_000))


def assert_ok(response):
    assert response.status_code < 400, response.text
    assert response.headers["X-Request-ID"].startswith("req_")
    return response.json()["data"]


def create_invite(
    *,
    key: str | None = None,
    target_user_id: uuid.UUID | None = None,
    expires_in_hours: int = 24,
) -> tuple[dict[str, object], dict[str, object]]:
    payload: dict[str, object] = {
        "purpose": "加入 Muchen Journey 探索营并完成 TSK-001",
        "expires_in_hours": expires_in_hours,
        "role": "LEARNER",
        "reviewer_id": str(REVIEWER_ID),
        "task_version_id": str(TASK_VERSION_ID),
        "target_user_id": str(target_user_id) if target_user_id else None,
    }
    idempotency_key = key or f"invite-{uuid.uuid4()}"
    response = client_for(f"operator-{uuid.uuid4()}").post(
        "/api/v1/ops/invites",
        headers={**operator_headers, "Idempotency-Key": idempotency_key},
        json=payload,
    )
    return assert_ok(response), payload


def exchange_and_confirm(invite_token: str, label: str) -> tuple[TestClient, dict[str, object], str]:
    learner = client_for(label)
    exchanged = assert_ok(
        learner.post(
            "/api/v1/join/exchange",
            json={"token": invite_token, "return_to": "/app"},
        )
    )
    assert exchanged["status"] == "PENDING_IDENTITY"
    assert "journey_next_join" in learner.cookies
    csrf_token = exchanged["csrf_token"]
    confirmed = assert_ok(
        learner.post(
            "/api/v1/identity/confirm",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "display_name": "真实邀请新人",
                "accepted_purpose": True,
                "return_to": "/app",
            },
        )
    )
    assert confirmed["enrollment_status"] == "ACTIVE"
    assert confirmed["roles"] == ["LEARNER"]
    assert SESSION_COOKIE in learner.cookies
    return learner, confirmed, csrf_token


def create_target_user(status: UserStatus, *, with_learner_role: bool) -> uuid.UUID:
    user_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(
            User(
                id=user_id,
                organization_id=ORGANIZATION_ID,
                display_name="已有 vNext 身份",
                status=status,
            )
        )
        session.flush()
        if with_learner_role:
            session.add(
                RoleAssignment(
                    id=uuid.uuid4(),
                    organization_id=ORGANIZATION_ID,
                    user_id=user_id,
                    role=Role.LEARNER,
                )
            )
    return user_id


def test_invite_create_is_idempotent_and_never_persists_plaintext_token():
    key = f"invite-idempotency-{uuid.uuid4()}"
    created, payload = create_invite(key=key)
    replay = assert_ok(
        client_for("operator-idempotency-replay").post(
            "/api/v1/ops/invites",
            headers={**operator_headers, "Idempotency-Key": key},
            json=payload,
        )
    )
    assert created["id"] == replay["id"]
    assert created["invite_token"] == replay["invite_token"]
    assert replay["idempotency_replay"] is True
    with SessionLocal() as session:
        invite = session.get(Invite, uuid.UUID(str(created["id"])))
        assert invite is not None
        assert invite.token_hash != created["invite_token"]
        assert session.scalar(select(func.count(Invite.id)).where(Invite.id == invite.id)) == 1


def test_concurrent_invite_create_replays_one_atomic_result():
    key = f"invite-concurrent-create-{uuid.uuid4()}"
    payload = {
        "purpose": "并发创建同一个受控邀请",
        "expires_in_hours": 24,
        "role": "LEARNER",
        "reviewer_id": str(REVIEWER_ID),
        "task_version_id": str(TASK_VERSION_ID),
        "target_user_id": None,
    }

    def create(label: str) -> tuple[int, dict[str, object]]:
        response = client_for(label).post(
            "/api/v1/ops/invites",
            headers={**operator_headers, "Idempotency-Key": key},
            json=payload,
        )
        return response.status_code, response.json()["data"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, ["invite-create-a", "invite-create-b"]))
    assert [status for status, _ in results] == [200, 200]
    assert results[0][1]["id"] == results[1][1]["id"]
    assert results[0][1]["invite_token"] == results[1][1]["invite_token"]
    assert sorted(result["idempotency_replay"] for _, result in results) == [False, True]


def test_real_invite_creates_internal_identity_session_and_csrf_protected_assignment():
    created, _ = create_invite()
    invite_token = str(created["invite_token"])
    learner = client_for("real-session-learner")
    exchanged = assert_ok(
        learner.post(
            "/api/v1/join/exchange",
            json={"token": invite_token, "return_to": "/app"},
        )
    )
    csrf_token = exchanged["csrf_token"]

    missing_csrf = learner.post(
        "/api/v1/identity/confirm",
        json={"display_name": "真实邀请新人", "accepted_purpose": True, "return_to": "/app"},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["error"]["code"] == "FORBIDDEN"

    confirmed = assert_ok(
        learner.post(
            "/api/v1/identity/confirm",
            headers={"X-CSRF-Token": csrf_token},
            json={"display_name": "真实邀请新人", "accepted_purpose": True, "return_to": "/app"},
        )
    )
    session_token = learner.cookies.get(SESSION_COOKIE)
    assert session_token
    session_view = assert_ok(learner.get("/api/v1/session"))
    assert session_view["user_id"] == confirmed["user_id"]
    assert session_view["safe_entry"] == "/app"
    assert session_view["csrf_required"] is True

    current = assert_ok(learner.get("/api/v1/me/current-action"))
    assignment_path = f"/api/v1/me/assignments/{current['resource_id']}/start"
    csrf_rejected = learner.post(
        assignment_path,
        headers={"Idempotency-Key": f"start-no-csrf-{uuid.uuid4()}"},
        json={"expected_revision": current["revision"]},
    )
    assert csrf_rejected.status_code == 403
    started = assert_ok(
        learner.post(
            assignment_path,
            headers={
                "Idempotency-Key": f"start-with-csrf-{uuid.uuid4()}",
                "X-CSRF-Token": confirmed["csrf_token"],
            },
            json={"expected_revision": current["revision"]},
        )
    )
    assert started["status"] == "IN_PROGRESS"

    with SessionLocal() as session:
        invite = session.get(Invite, uuid.UUID(str(created["id"])))
        assert invite is not None and invite.status == InviteStatus.CONSUMED
        assert session.scalar(
            select(ExternalIdentity.id).where(
                ExternalIdentity.user_id == uuid.UUID(str(confirmed["user_id"])),
                ExternalIdentity.provider == "INVITE",
            )
        )
        stored_session = session.scalar(
            select(IdentitySession).where(
                IdentitySession.user_id == uuid.UUID(str(confirmed["user_id"]))
            )
        )
        assert stored_session is not None and stored_session.token_hash != session_token
        event_types = set(
            session.scalars(
                select(OutboxEvent.event_type).where(
                    OutboxEvent.aggregate_id.in_([invite.id, uuid.UUID(str(confirmed["user_id"]))])
                )
            )
        )
        assert {"invite.consumed.v1", "identity.confirmed.v1"} <= event_types
        assert session.scalar(
            select(AuditEntry.id).where(
                AuditEntry.action == "identity.confirmed",
                AuditEntry.actor_id == uuid.UUID(str(confirmed["user_id"])),
            )
        )

    consumed_again = client_for("consumed-invite-replay").post(
        "/api/v1/join/exchange",
        json={"token": invite_token, "return_to": "/app"},
    )
    assert consumed_again.status_code == 410

    logged_out = assert_ok(
        learner.post(
            "/api/v1/session/logout",
            headers={"X-CSRF-Token": confirmed["csrf_token"]},
        )
    )
    assert logged_out["status"] == "LOGGED_OUT"
    assert learner.get("/api/v1/session").status_code == 401


def test_invalid_expired_and_revoked_invites_create_no_active_enrollment():
    with SessionLocal() as session:
        initial_count = session.scalar(select(func.count(Enrollment.id)))

    invalid = client_for("invalid-invite").post(
        "/api/v1/join/exchange",
        json={"token": "x" * 43, "return_to": "/app"},
    )
    assert invalid.status_code == 410

    expired, _ = create_invite()
    with SessionLocal.begin() as session:
        invite = session.get(Invite, uuid.UUID(str(expired["id"])))
        assert invite is not None
        invite.expires_at = utc_now() - timedelta(minutes=1)
    expired_response = client_for("expired-invite").post(
        "/api/v1/join/exchange",
        json={"token": expired["invite_token"], "return_to": "/app"},
    )
    assert expired_response.status_code == 410

    revoked, _ = create_invite()
    revoked_result = assert_ok(
        client_for("operator-revoke").post(
            f"/api/v1/ops/invites/{revoked['id']}/revoke",
            headers={**operator_headers, "Idempotency-Key": f"revoke-{uuid.uuid4()}"},
            json={"expected_revision": revoked["revision"], "reason": "受邀对象已不参加本次探索营"},
        )
    )
    assert revoked_result["status"] == "REVOKED"
    revoked_response = client_for("revoked-invite").post(
        "/api/v1/join/exchange",
        json={"token": revoked["invite_token"], "return_to": "/app"},
    )
    assert revoked_response.status_code == 410

    with SessionLocal() as session:
        final_count = session.scalar(select(func.count(Enrollment.id)))
        expired_invite = session.get(Invite, uuid.UUID(str(expired["id"])))
        assert final_count == initial_count
        assert expired_invite is not None and expired_invite.status == InviteStatus.EXPIRED


def test_concurrent_invite_exchange_has_one_winner_and_revoke_cleans_pending_enrollment():
    created, _ = create_invite()
    token = str(created["invite_token"])

    def exchange(label: str) -> int:
        return client_for(label).post(
            "/api/v1/join/exchange",
            json={"token": token, "return_to": "/app"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = sorted(executor.map(exchange, ["concurrent-a", "concurrent-b"]))
    assert statuses == [200, 410]

    revoked = assert_ok(
        client_for("operator-concurrent-revoke").post(
            f"/api/v1/ops/invites/{created['id']}/revoke",
            headers={**operator_headers, "Idempotency-Key": f"revoke-{uuid.uuid4()}"},
            json={"expected_revision": created["revision"], "reason": "并发交换验证结束，撤销测试邀请"},
        )
    )
    assert revoked["status"] == "REVOKED"
    with SessionLocal() as session:
        context = session.scalar(
            select(JoinContext).where(JoinContext.invite_id == uuid.UUID(str(created["id"])))
        )
        assert context is not None
        enrollment = session.get(Enrollment, context.enrollment_id)
        assert enrollment is not None and enrollment.status == EnrollmentStatus.CANCELLED


def test_existing_identity_is_reused_and_disabled_identity_is_rejected():
    existing_user_id = create_target_user(UserStatus.ACTIVE, with_learner_role=True)
    existing_invite, _ = create_invite(target_user_id=existing_user_id)
    learner, confirmed, _ = exchange_and_confirm(
        str(existing_invite["invite_token"]), "existing-vnext-user"
    )
    assert confirmed["user_id"] == str(existing_user_id)
    session_view = assert_ok(learner.get("/api/v1/session"))
    assert session_view["display_name"] == "已有 vNext 身份"

    disabled_user_id = create_target_user(UserStatus.DISABLED, with_learner_role=False)
    disabled_invite, _ = create_invite(target_user_id=disabled_user_id)
    disabled = client_for("disabled-vnext-user").post(
        "/api/v1/join/exchange",
        json={"token": disabled_invite["invite_token"], "return_to": "/app"},
    )
    assert disabled.status_code == 403
    assert disabled.json()["error"]["code"] == "FORBIDDEN"


def test_old_credentials_open_redirect_and_state_replay_are_rejected():
    old_credentials = client_for("old-credentials")
    old_credentials.cookies.set("legacy_session", "legacy-token")
    response = old_credentials.get(
        "/api/v1/session",
        headers={"Authorization": "Bearer legacy-token"},
    )
    assert response.status_code == 401

    invalid_vnext = client_for("invalid-vnext-session")
    invalid_vnext.cookies.set(SESSION_COOKIE, "not-a-real-vnext-session")
    response = invalid_vnext.get("/api/v1/session", headers={"X-Fixture-Role": "LEARNER"})
    assert response.status_code == 401

    created, _ = create_invite()
    malicious_return = client_for("malicious-return").post(
        "/api/v1/join/exchange",
        json={"token": created["invite_token"], "return_to": "https://attacker.invalid"},
    )
    assert malicious_return.status_code == 422

    exchange_client = client_for("join-state-replay")
    first = exchange_client.post(
        "/api/v1/join/exchange",
        json={"token": created["invite_token"], "return_to": "/app"},
    )
    assert first.status_code == 200
    second = exchange_client.post(
        "/api/v1/join/exchange",
        json={"token": created["invite_token"], "return_to": "/app"},
    )
    assert second.status_code == 410


def test_invite_exchange_rate_limit_returns_retryable_429():
    settings = get_settings()
    rate_client = client_for("rate-limited-client")
    statuses = [
        rate_client.post(
            "/api/v1/join/exchange",
            json={"token": f"invalid-rate-token-{attempt:024d}", "return_to": "/app"},
        ).status_code
        for attempt in range(settings.invite_exchange_limit + 1)
    ]
    assert statuses[:-1] == [410] * settings.invite_exchange_limit
    assert statuses[-1] == 429
    limited = rate_client.post(
        "/api/v1/join/exchange",
        json={"token": "invalid-rate-token-after-limit-0000", "return_to": "/app"},
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["retryable"] is True
