#!/usr/bin/env python3
"""Bootstrap three controlled-Canary identities without exposing secrets."""

from __future__ import annotations

import argparse
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


CANDIDATE = "9e2d3496f5df80da1291c77bd6f949a5078ef25d"
CANARY_DATABASE = "journey_next_canary_20260901_c72fea5"
CONFIRMATION = "BOOTSTRAP_IDENTITIES_0E86352_PRODUCTION_CANARY"
_FIELDS = {
    "operator_user_id",
    "operator_display_name",
    "learner_user_id",
    "learner_display_name",
    "owner_user_id",
    "owner_display_name",
    "authorization_reference",
    "expires_in_minutes",
}
_AUTHORIZATION_REFERENCE = re.compile(r"^[A-Za-z0-9._:-]{8,120}$")


class BootstrapError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootstrapRequest:
    operator_user_id: uuid.UUID
    operator_display_name: str
    learner_user_id: uuid.UUID
    learner_display_name: str
    owner_user_id: uuid.UUID
    owner_display_name: str
    authorization_reference: str
    expires_in_minutes: int


def _uuid_v4(value: object, field: str) -> uuid.UUID:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as error:
        raise BootstrapError(f"{field} must be UUIDv4") from error
    if parsed.version != 4:
        raise BootstrapError(f"{field} must be UUIDv4")
    return parsed


def _display_name(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise BootstrapError(f"{field} display name is invalid")
    normalized = value.strip()
    if not 1 <= len(normalized) <= 120 or any(ord(char) < 32 for char in normalized):
        raise BootstrapError(f"{field} display name is invalid")
    return normalized


def parse_payload(payload: object) -> BootstrapRequest:
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise BootstrapError("bootstrap request fields differ")
    operator_id = _uuid_v4(payload["operator_user_id"], "operator_user_id")
    learner_id = _uuid_v4(payload["learner_user_id"], "learner_user_id")
    owner_id = _uuid_v4(payload["owner_user_id"], "owner_user_id")
    if len({operator_id, learner_id, owner_id}) != 3:
        raise BootstrapError("operator, learner, and owner user IDs must differ")
    operator_name = _display_name(payload["operator_display_name"], "operator")
    learner_name = _display_name(payload["learner_display_name"], "learner")
    owner_name = _display_name(payload["owner_display_name"], "owner")
    if len({operator_name, learner_name, owner_name}) != 3:
        raise BootstrapError("operator, learner, and owner display names must differ")
    authorization_reference = payload["authorization_reference"]
    if not isinstance(authorization_reference, str) or not _AUTHORIZATION_REFERENCE.fullmatch(
        authorization_reference
    ):
        raise BootstrapError("authorization reference must be a non-sensitive stable identifier")
    expires_in_minutes = payload["expires_in_minutes"]
    if isinstance(expires_in_minutes, bool) or not isinstance(expires_in_minutes, int):
        raise BootstrapError("bootstrap link lifetime must be 5-30 minutes")
    if not 5 <= expires_in_minutes <= 30:
        raise BootstrapError("bootstrap link lifetime must be 5-30 minutes")
    return BootstrapRequest(
        operator_user_id=operator_id,
        operator_display_name=operator_name,
        learner_user_id=learner_id,
        learner_display_name=learner_name,
        owner_user_id=owner_id,
        owner_display_name=owner_name,
        authorization_reference=authorization_reference,
        expires_in_minutes=expires_in_minutes,
    )


def parse_request(path: Path) -> BootstrapRequest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BootstrapError("bootstrap request is not valid JSON") from error
    return parse_payload(payload)


def validate_runtime(
    database_url: str,
    *,
    app_env: str,
    release_marker: str,
    confirmation: str,
    database_kind: str = "source",
) -> None:
    if confirmation != CONFIRMATION:
        raise BootstrapError(f"confirmation must be {CONFIRMATION}")
    if app_env != "production" or release_marker != "PRODUCTION_CANARY_UAT":
        raise BootstrapError("identity bootstrap requires production Canary configuration")
    if not isinstance(database_url, str) or "\n" in database_url or "\r" in database_url:
        raise BootstrapError("Canary database URL is invalid")
    parsed = urlsplit(database_url)
    if parsed.scheme != "postgresql+psycopg" or parsed.hostname in {
        None,
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise BootstrapError("Canary database host is invalid")
    if parsed.username != "journey_next_migrator":
        raise BootstrapError("Canary database credentials are invalid")
    if database_kind != "canary" or parsed.path != f"/{CANARY_DATABASE}":
        raise BootstrapError("Canary database must be the exact isolated database")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get("sslmode") != ["verify-full"]:
        raise BootstrapError("Canary database must use sslmode=verify-full")
    if query.get("sslrootcert") != ["/run/secrets/volcengine-rds-ca.pem"]:
        raise BootstrapError("Canary database CA path is invalid")


def public_result(result: dict[str, object]) -> dict[str, object]:
    """Select the encrypted response fields; names and request material never leave the DB job."""
    fields = (
        "operator_user_id",
        "learner_user_id",
        "owner_user_id",
        "operator_roles",
        "owner_roles",
        "operator_link_id",
        "operator_link_start_path",
        "operator_link_expires_at",
        "expires_in_minutes",
    )
    return {field: result[field] for field in fields}


def bootstrap(session: object, request: BootstrapRequest, secret: str, now: datetime | None = None) -> dict[str, object]:
    """Create ACTIVE operator/reviewer, bare learner target, and owner learner/reviewer."""
    if len(secret) < 32 or "\n" in secret or "\r" in secret:
        raise BootstrapError("identity subject secret is invalid")
    # Imports stay inside the operation so request validation remains dependency-light and testable.
    from sqlalchemy import select

    from journey_api.identity import add_audit, utc_now
    from journey_api.models import Organization, Role, RoleAssignment, User, UserStatus
    from journey_api.wp09_bootstrap import create_operator_link

    issued_at = now or utc_now()
    organizations = session.scalars(select(Organization)).all()
    if len(organizations) != 1:
        raise BootstrapError("identity bootstrap requires exactly one organization")
    organization = organizations[0]
    for user_id in (request.operator_user_id, request.learner_user_id, request.owner_user_id):
        if session.scalar(select(User.id).where(User.id == user_id)) is not None:
            raise BootstrapError("requested user ID already exists; bootstrap is not replayable")

    operator = User(
        id=request.operator_user_id,
        organization_id=organization.id,
        display_name=request.operator_display_name,
        status=UserStatus.ACTIVE,
    )
    learner = User(
        id=request.learner_user_id,
        organization_id=organization.id,
        display_name=request.learner_display_name,
        status=UserStatus.ACTIVE,
    )
    owner = User(
        id=request.owner_user_id,
        organization_id=organization.id,
        display_name=request.owner_display_name,
        status=UserStatus.ACTIVE,
    )
    session.add_all([operator, learner, owner])
    session.flush()
    session.add_all(
        [
            RoleAssignment(
                id=uuid.uuid4(), organization_id=organization.id, user_id=operator.id, role=Role.OPERATOR
            ),
            RoleAssignment(
                id=uuid.uuid4(), organization_id=organization.id, user_id=operator.id, role=Role.REVIEWER
            ),
            RoleAssignment(
                id=uuid.uuid4(), organization_id=organization.id, user_id=owner.id, role=Role.LEARNER
            ),
            RoleAssignment(
                id=uuid.uuid4(), organization_id=organization.id, user_id=owner.id, role=Role.REVIEWER
            ),
        ]
    )
    add_audit(
        session,
        request_id=f"wp31-identity-bootstrap:{uuid.uuid4()}",
        organization_id=organization.id,
        action="identity.bootstrap_operator_created",
        resource_type="user",
        resource_id=operator.id,
        result="SUCCESS",
        details={"roles": [Role.OPERATOR.value, Role.REVIEWER.value], "authorization_reference": request.authorization_reference},
    )
    add_audit(
        session,
        request_id=f"wp31-identity-bootstrap:{uuid.uuid4()}",
        organization_id=organization.id,
        action="identity.bootstrap_learner_target_created",
        resource_type="user",
        resource_id=learner.id,
        result="SUCCESS",
        details={"status": UserStatus.ACTIVE.value, "role_assignment": False, "authorization_reference": request.authorization_reference},
    )
    add_audit(
        session,
        request_id=f"wp31-identity-bootstrap:{uuid.uuid4()}",
        organization_id=organization.id,
        action="identity.bootstrap_owner_created",
        resource_type="user",
        resource_id=owner.id,
        result="SUCCESS",
        details={"roles": [Role.LEARNER.value, Role.REVIEWER.value], "authorization_reference": request.authorization_reference},
    )
    link = create_operator_link(
        session,
        target_user_id=operator.id,
        secret=secret,
        authorization_reference=request.authorization_reference,
        expires_in_minutes=request.expires_in_minutes,
        now=issued_at,
    )
    return public_result(
        {
            "operator_user_id": str(operator.id),
            "learner_user_id": str(learner.id),
            "owner_user_id": str(owner.id),
            "owner_roles": [Role.LEARNER.value, Role.REVIEWER.value],
            "operator_roles": [Role.OPERATOR.value, Role.REVIEWER.value],
            "operator_link_id": link["link_id"],
            "operator_link_start_path": link["start_path"],
            "operator_link_expires_at": link["expires_at"],
            "expires_in_minutes": request.expires_in_minutes,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--database-kind", choices=("canary",), default="canary")
    args = parser.parse_args()
    try:
        # Runtime configuration is read only after parsing the sealed request.
        from journey_api.config import get_settings
        from journey_api.db import SessionLocal

        settings = get_settings()
        validate_runtime(
            settings.database_url,
            app_env=settings.app_env,
            release_marker=settings.release_marker,
            confirmation=args.confirm,
            database_kind=args.database_kind,
        )
        request = parse_request(args.request)
        with SessionLocal() as session:
            result = bootstrap(session, request, settings.identity_subject_secret)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (BootstrapError, OSError, ValueError, TypeError) as error:
        print(f"WP31_IDENTITY_BOOTSTRAP=FAIL reason={error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
