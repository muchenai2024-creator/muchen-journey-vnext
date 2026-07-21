from __future__ import annotations

import argparse
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from journey_api.db import SessionLocal
from journey_api.models import (
    LocalNotificationReceipt,
    NotificationAttempt,
    NotificationAttemptStatus,
    NotificationChannel,
    NotificationDelivery,
    NotificationStatus,
    OutboxEvent,
    OutboxStatus,
    WorkerHeartbeat,
)


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("journey_worker")


def positive_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class WorkerSettings:
    app_env: str
    app_release: str
    adapter: str
    local_behavior: str
    max_attempts: int
    retry_base_seconds: int
    lease_seconds: int
    poll_seconds: int
    crash_after_delivery: bool

    @classmethod
    def from_env(cls) -> "WorkerSettings":
        settings = cls(
            app_env=os.getenv("APP_ENV", "local"),
            app_release=os.getenv("APP_RELEASE", "dev"),
            adapter=os.getenv("NOTIFICATION_ADAPTER", "LOCAL_TEST").upper(),
            local_behavior=os.getenv("LOCAL_NOTIFICATION_BEHAVIOR", "success").lower(),
            max_attempts=positive_int("NOTIFICATION_MAX_ATTEMPTS", 3, minimum=1),
            retry_base_seconds=positive_int("NOTIFICATION_RETRY_BASE_SECONDS", 5),
            lease_seconds=positive_int("OUTBOX_LEASE_SECONDS", 30, minimum=1),
            poll_seconds=positive_int("WORKER_POLL_SECONDS", 2, minimum=1),
            crash_after_delivery=os.getenv("WORKER_TEST_CRASH_AFTER_DELIVERY", "false").lower()
            == "true",
        )
        if settings.app_env not in {"local", "test", "staging", "production"}:
            raise ValueError("APP_ENV must be local, test, staging, or production")
        if settings.adapter not in {"LOCAL_TEST", "DISABLED"}:
            raise ValueError("NOTIFICATION_ADAPTER must be LOCAL_TEST or DISABLED")
        if settings.adapter == "LOCAL_TEST" and settings.app_env not in {"local", "test"}:
            raise ValueError("LOCAL_TEST notification adapter is disabled outside local/test")
        if settings.adapter == "DISABLED" and settings.app_env != "staging":
            raise ValueError("DISABLED notification adapter is staging-only")
        if settings.local_behavior not in {"success", "fail_once", "always_fail"}:
            raise ValueError("LOCAL_NOTIFICATION_BEHAVIOR is invalid")
        if settings.crash_after_delivery and settings.app_env not in {"local", "test"}:
            raise ValueError("Worker crash injection is local/test only")
        return settings


def record_heartbeat(settings: WorkerSettings, status: str) -> None:
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        statement = insert(WorkerHeartbeat).values(
            worker_name="notification-worker",
            release=settings.app_release,
            status=status,
            last_seen_at=now,
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[WorkerHeartbeat.worker_name],
                set_={
                    "release": statement.excluded.release,
                    "status": statement.excluded.status,
                    "last_seen_at": statement.excluded.last_seen_at,
                },
            )
        )


@dataclass(frozen=True)
class ClaimedEvent:
    id: uuid.UUID
    event_type: str
    lock_token: uuid.UUID
    attempt_number: int
    dedupe_key: str


class LocalDeliveryError(RuntimeError):
    code = "LOCAL_ADAPTER_UNAVAILABLE"


def notification_for_update(session: Session, event_id: uuid.UUID) -> NotificationDelivery | None:
    return session.scalar(
        select(NotificationDelivery)
        .where(NotificationDelivery.event_id == event_id)
        .with_for_update()
    )


def record_attempt_once(
    session: Session,
    *,
    delivery_id: uuid.UUID,
    attempt_number: int,
    status: NotificationAttemptStatus,
    error_code: str | None,
    attempted_at: datetime,
) -> None:
    existing = session.scalar(
        select(NotificationAttempt.id).where(
            NotificationAttempt.delivery_id == delivery_id,
            NotificationAttempt.attempt_number == attempt_number,
        )
    )
    if existing is None:
        session.add(
            NotificationAttempt(
                id=uuid.uuid4(),
                delivery_id=delivery_id,
                attempt_number=attempt_number,
                status=status,
                error_code=error_code,
                attempted_at=attempted_at,
            )
        )


def claim_next(
    settings: WorkerSettings, *, event_id: uuid.UUID | None = None
) -> ClaimedEvent | None:
    now = datetime.now(UTC)
    lease_cutoff = now - timedelta(seconds=settings.lease_seconds)
    eligible = or_(
        and_(
            OutboxEvent.status == OutboxStatus.PENDING,
            or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
        ),
        and_(
            OutboxEvent.status == OutboxStatus.FAILED,
            OutboxEvent.next_attempt_at.is_not(None),
            OutboxEvent.next_attempt_at <= now,
        ),
        and_(
            OutboxEvent.status == OutboxStatus.PROCESSING,
            OutboxEvent.locked_at.is_not(None),
            OutboxEvent.locked_at <= lease_cutoff,
        ),
    )
    with SessionLocal.begin() as session:
        query = (
            select(OutboxEvent)
            .where(eligible)
            .order_by(OutboxEvent.next_attempt_at, OutboxEvent.occurred_at, OutboxEvent.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if settings.adapter == "DISABLED":
            query = query.where(OutboxEvent.event_type != "notification.requested.v1")
        if event_id is not None:
            query = query.where(OutboxEvent.id == event_id)
        event = session.scalar(query)
        if event is None:
            return None

        delivery = notification_for_update(session, event.id)
        if event.status == OutboxStatus.PROCESSING and delivery is not None:
            record_attempt_once(
                session,
                delivery_id=delivery.id,
                attempt_number=event.attempt_count,
                status=NotificationAttemptStatus.LEASE_EXPIRED,
                error_code="WORKER_LEASE_EXPIRED",
                attempted_at=now,
            )

        event.attempt_count += 1
        event.status = OutboxStatus.PROCESSING
        event.lock_token = uuid.uuid4()
        event.locked_at = now
        event.next_attempt_at = None
        event.last_error_code = None
        if delivery is not None:
            delivery.status = NotificationStatus.SENDING
            delivery.attempt_count = event.attempt_count
            delivery.next_attempt_at = None
            delivery.last_error_code = None
            delivery.updated_at = now
        return ClaimedEvent(
            id=event.id,
            event_type=event.event_type,
            lock_token=event.lock_token,
            attempt_number=event.attempt_count,
            dedupe_key=event.dedupe_key or f"event:{event.id}",
        )


def deliver_local_notification(
    claimed: ClaimedEvent, settings: WorkerSettings
) -> bool:
    with SessionLocal.begin() as session:
        delivery = session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.event_id == claimed.id
            )
        )
        if delivery is None:
            raise LocalDeliveryError("notification delivery is missing")
        if delivery.channel != NotificationChannel.LOCAL_TEST:
            raise LocalDeliveryError("unsupported notification channel")
        existing = session.scalar(
            select(LocalNotificationReceipt.id).where(
                LocalNotificationReceipt.dedupe_key == claimed.dedupe_key
            )
        )
        if existing is not None:
            return True
        if settings.local_behavior == "always_fail" or (
            settings.local_behavior == "fail_once" and claimed.attempt_number == 1
        ):
            raise LocalDeliveryError("local test adapter failure")
        session.add(
            LocalNotificationReceipt(
                id=uuid.uuid4(),
                delivery_id=delivery.id,
                dedupe_key=claimed.dedupe_key,
            )
        )
    return False


def finalize_success(claimed: ClaimedEvent, *, deduplicated: bool) -> bool:
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        event = session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.id == claimed.id,
                OutboxEvent.status == OutboxStatus.PROCESSING,
                OutboxEvent.lock_token == claimed.lock_token,
            )
            .with_for_update()
        )
        if event is None:
            return False
        delivery = notification_for_update(session, event.id)
        event.status = OutboxStatus.SENT
        event.processed_at = now
        event.locked_at = None
        event.lock_token = None
        event.next_attempt_at = None
        event.last_error_code = None
        if delivery is not None:
            delivery.status = NotificationStatus.DELIVERED
            delivery.delivered_at = now
            delivery.next_attempt_at = None
            delivery.last_error_code = None
            delivery.updated_at = now
            record_attempt_once(
                session,
                delivery_id=delivery.id,
                attempt_number=claimed.attempt_number,
                status=NotificationAttemptStatus.DELIVERED,
                error_code=None,
                attempted_at=now,
            )
    logger.info(
        "outbox processed event_type=%s attempt=%s deduplicated=%s",
        claimed.event_type,
        claimed.attempt_number,
        deduplicated,
    )
    return True


def finalize_failure(
    claimed: ClaimedEvent, settings: WorkerSettings, *, error_code: str
) -> bool:
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        event = session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.id == claimed.id,
                OutboxEvent.status == OutboxStatus.PROCESSING,
                OutboxEvent.lock_token == claimed.lock_token,
            )
            .with_for_update()
        )
        if event is None:
            return False
        delivery = notification_for_update(session, event.id)
        is_final = claimed.attempt_number >= settings.max_attempts
        delay = settings.retry_base_seconds * (2 ** max(claimed.attempt_number - 1, 0))
        next_attempt = None if is_final else now + timedelta(seconds=min(delay, 3600))
        event.status = OutboxStatus.FAILED
        event.processed_at = now if is_final else None
        event.locked_at = None
        event.lock_token = None
        event.next_attempt_at = next_attempt
        event.last_error_code = error_code
        if delivery is not None:
            delivery.status = (
                NotificationStatus.DEAD if is_final else NotificationStatus.RETRY_WAIT
            )
            delivery.next_attempt_at = next_attempt
            delivery.last_error_code = error_code
            delivery.updated_at = now
            record_attempt_once(
                session,
                delivery_id=delivery.id,
                attempt_number=claimed.attempt_number,
                status=(
                    NotificationAttemptStatus.FAILED_FINAL
                    if is_final
                    else NotificationAttemptStatus.FAILED_RETRYABLE
                ),
                error_code=error_code,
                attempted_at=now,
            )
    logger.warning(
        "outbox attempt failed event_type=%s attempt=%s final=%s error_code=%s",
        claimed.event_type,
        claimed.attempt_number,
        is_final,
        error_code,
    )
    return True


def process_claimed(claimed: ClaimedEvent, settings: WorkerSettings) -> bool:
    if claimed.event_type != "notification.requested.v1":
        return finalize_success(claimed, deduplicated=False)
    try:
        deduplicated = deliver_local_notification(claimed, settings)
    except LocalDeliveryError:
        return finalize_failure(
            claimed, settings, error_code=LocalDeliveryError.code
        )
    if settings.crash_after_delivery:
        raise RuntimeError("local/test worker crash injection after adapter commit")
    return finalize_success(claimed, deduplicated=deduplicated)


def process_batch(
    limit: int = 20,
    *,
    event_id: uuid.UUID | None = None,
    settings: WorkerSettings | None = None,
) -> int:
    worker_settings = settings or WorkerSettings.from_env()
    processed = 0
    for _ in range(limit):
        claimed = claim_next(worker_settings, event_id=event_id)
        if claimed is None:
            break
        if process_claimed(claimed, worker_settings):
            processed += 1
        if event_id is not None:
            break
    return processed


def run() -> None:
    settings = WorkerSettings.from_env()
    logger.info("worker started adapter=%s", settings.adapter)
    record_heartbeat(settings, "RUNNING")
    while True:
        processed = process_batch(settings=settings)
        record_heartbeat(settings, "RUNNING" if processed else "IDLE")
        if processed == 0:
            time.sleep(settings.poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consume the vNext transactional outbox")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--event-id", type=uuid.UUID)
    args = parser.parse_args()
    settings = WorkerSettings.from_env()
    if args.limit < 1 or args.limit > 100:
        parser.error("--limit must be between 1 and 100")
    if args.event_id is not None and settings.app_env not in {"local", "test"}:
        parser.error("--event-id is local/test only")
    if args.once:
        record_heartbeat(settings, "RUNNING")
        processed = process_batch(
            limit=args.limit, event_id=args.event_id, settings=settings
        )
        record_heartbeat(settings, "IDLE")
        logger.info("worker once complete processed=%s", processed)
        return
    if args.event_id is not None:
        parser.error("--event-id requires --once")
    run()


if __name__ == "__main__":
    main()
