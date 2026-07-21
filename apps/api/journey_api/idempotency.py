import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.errors import ApiError
from journey_api.models import IdempotencyRecord


def canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def find_replay(
    session: Session,
    *,
    actor_id: uuid.UUID,
    command: str,
    key: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if not 8 <= len(key) <= 120:
        raise ApiError(400, "INVALID_REQUEST", "Idempotency-Key 长度必须为 8–120。")
    record = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.command == command,
            IdempotencyRecord.key == key,
        )
    )
    if record is None:
        return None
    if record.request_hash != canonical_hash(payload):
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "同一幂等键不能用于不同请求。")
    replay = dict(record.response_body)
    replay["idempotency_replay"] = True
    return replay


def store_result(
    session: Session,
    *,
    actor_id: uuid.UUID,
    command: str,
    key: str,
    payload: dict[str, Any],
    response: dict[str, Any],
) -> None:
    session.add(
        IdempotencyRecord(
            id=uuid.uuid4(),
            actor_id=actor_id,
            command=command,
            key=key,
            request_hash=canonical_hash(payload),
            response_body=response,
        )
    )

