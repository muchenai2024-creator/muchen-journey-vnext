from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    AuditEntry,
    Enrollment,
    EnrollmentStatus,
    ImportBatch,
    ImportRecord,
    Organization,
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


DATA_PATH = "data/enrollments.ndjson"
MAX_MANIFEST_BYTES = 16_384
MAX_CHECKSUM_BYTES = 4_096
MAX_SIGNATURE_BYTES = 256
MAX_DATA_BYTES = 5 * 1024 * 1024
MAX_RECORDS = 1_000
SOURCE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{3,120}$")


class PackageError(RuntimeError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportManifest(StrictModel):
    schema_version: Literal[1]
    package_id: uuid.UUID
    source_kind: Literal["SYNTHETIC_VNEXT_FIXTURE"]
    source_revision: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    created_at: datetime
    target_environment: Literal["local", "test"]
    target_organization_id: uuid.UUID
    operator_id: uuid.UUID
    record_count: int = Field(ge=1, le=MAX_RECORDS)
    data_file: Literal[DATA_PATH]

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        return value


class EnrollmentImportRecord(StrictModel):
    source_key: str = Field(min_length=3, max_length=120)
    learner_display_name: str = Field(min_length=1, max_length=120)
    reviewer_id: uuid.UUID
    task_version_id: uuid.UUID

    @field_validator("source_key")
    @classmethod
    def validate_source_key(cls, value: str) -> str:
        normalized = value.strip()
        if not SOURCE_KEY_PATTERN.fullmatch(normalized):
            raise ValueError("source_key has invalid characters")
        return normalized

    @field_validator("learner_display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("learner_display_name cannot be blank")
        return normalized


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def file_bytes(path: Path, *, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PackageError(f"required regular file is missing: {path.name}")
    size = path.stat().st_size
    if size < 1 or size > maximum:
        raise PackageError(f"package file size is invalid: {path.name}")
    return path.read_bytes()


def package_files(package_dir: Path) -> tuple[bytes, bytes, bytes, bytes]:
    if package_dir.is_symlink() or not package_dir.is_dir():
        raise PackageError("package path must be a regular directory")
    expected = {"manifest.json", "checksums.sha256", "signature", "data"}
    actual = {item.name for item in package_dir.iterdir()}
    if actual != expected:
        raise PackageError("package contains missing or unexpected top-level entries")
    data_dir = package_dir / "data"
    if data_dir.is_symlink() or not data_dir.is_dir():
        raise PackageError("package data path must be a regular directory")
    if {item.name for item in data_dir.iterdir()} != {"enrollments.ndjson"}:
        raise PackageError("package data directory contains unexpected entries")
    return (
        file_bytes(package_dir / "manifest.json", maximum=MAX_MANIFEST_BYTES),
        file_bytes(package_dir / "checksums.sha256", maximum=MAX_CHECKSUM_BYTES),
        file_bytes(package_dir / "signature", maximum=MAX_SIGNATURE_BYTES),
        file_bytes(package_dir / DATA_PATH, maximum=MAX_DATA_BYTES),
    )


def verify_package(package_dir: Path) -> tuple[ImportManifest, list[EnrollmentImportRecord], str]:
    settings = get_settings()
    if settings.app_env not in {"local", "test"}:
        raise PackageError("offline importer is disabled outside local/test")
    manifest_bytes, checksum_bytes, signature_bytes, data_bytes = package_files(package_dir)
    expected_checksum_line = f"{hashlib.sha256(data_bytes).hexdigest()}  {DATA_PATH}\n".encode()
    if not hmac.compare_digest(checksum_bytes, expected_checksum_line):
        raise PackageError("package checksum manifest does not match data")
    signed_payload = manifest_bytes + b"\n" + checksum_bytes
    expected_signature = hmac.new(
        settings.import_signing_key.encode(), signed_payload, hashlib.sha256
    ).hexdigest().encode()
    if not hmac.compare_digest(signature_bytes.strip(), expected_signature):
        raise PackageError("package signature is invalid")
    try:
        manifest = ImportManifest.model_validate(json.loads(manifest_bytes))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise PackageError("manifest schema is invalid") from exc
    if manifest.target_environment != settings.app_env:
        raise PackageError("package target environment does not match runtime")
    lines = data_bytes.splitlines()
    if len(lines) != manifest.record_count:
        raise PackageError("manifest record count does not match data")
    records: list[EnrollmentImportRecord] = []
    try:
        for line in lines:
            if not line or len(line) > 16_384:
                raise PackageError("import record line size is invalid")
            records.append(EnrollmentImportRecord.model_validate(json.loads(line)))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise PackageError("import record schema is invalid") from exc
    keys = [record.source_key for record in records]
    if len(keys) != len(set(keys)):
        raise PackageError("package contains duplicate source keys")
    package_checksum = hashlib.sha256(signed_payload + b"\n" + signature_bytes.strip()).hexdigest()
    return manifest, records, package_checksum


def record_hash(record: EnrollmentImportRecord) -> str:
    return hashlib.sha256(canonical_json(record.model_dump(mode="json"))).hexdigest()


def safe_report(
    *,
    package_checksum: str,
    status: str,
    record_count: int,
    imported_count: int,
    replayed_count: int,
    quarantined_count: int,
    reasons: Counter[str],
    package_replay: bool,
    mode: Literal["DRY_RUN", "APPLY"],
    would_import_count: int = 0,
) -> dict[str, object]:
    return {
        "contract": "journey-next-offline-import-v1",
        "package_checksum": package_checksum,
        "mode": mode,
        "status": status,
        "record_count": record_count,
        "imported_count": imported_count,
        "replayed_count": replayed_count,
        "quarantined_count": quarantined_count,
        "quarantine_reason_counts": dict(sorted(reasons.items())),
        "would_import_count": would_import_count,
        "package_replay": package_replay,
        "contains_record_identifiers": False,
        "source_writeback_executed": False,
        "external_network_access_executed": False,
    }


def dry_run_package(package_dir: Path) -> dict[str, object]:
    manifest, records, package_checksum = verify_package(package_dir)
    with SessionLocal() as session:
        organization = session.get(Organization, manifest.target_organization_id)
        operator = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(
                User.id == manifest.operator_id,
                User.organization_id == manifest.target_organization_id,
                User.status == UserStatus.ACTIVE,
                RoleAssignment.organization_id == manifest.target_organization_id,
                RoleAssignment.role == Role.OPERATOR,
            )
        )
        if organization is None or operator is None:
            raise PackageError("package target organization or operator scope is invalid")
        existing_batch = session.scalar(
            select(ImportBatch).where(ImportBatch.package_id == manifest.package_id)
        )
        if existing_batch is not None:
            if existing_batch.package_checksum != package_checksum:
                raise PackageError("package id was reused with different signed content")
            reasons = Counter(
                session.scalars(
                    select(ImportRecord.reason_code).where(
                        ImportRecord.batch_id == existing_batch.id,
                        ImportRecord.reason_code.is_not(None),
                    )
                ).all()
            )
            return safe_report(
                package_checksum=package_checksum,
                status="DRY_RUN_PACKAGE_REPLAY",
                record_count=existing_batch.record_count,
                imported_count=0,
                replayed_count=existing_batch.imported_count + existing_batch.replayed_count,
                quarantined_count=existing_batch.quarantined_count,
                reasons=reasons,
                package_replay=True,
                mode="DRY_RUN",
            )
        would_import = 0
        replayed = 0
        quarantined = 0
        reasons: Counter[str] = Counter()
        for item in records:
            fingerprint = record_hash(item)
            prior = session.scalar(
                select(ImportRecord)
                .where(
                    ImportRecord.organization_id == manifest.target_organization_id,
                    ImportRecord.source_namespace == manifest.source_kind,
                    ImportRecord.source_key == item.source_key,
                    ImportRecord.status.in_(["IMPORTED", "REPLAYED"]),
                )
                .order_by(ImportRecord.created_at.desc(), ImportRecord.id)
            )
            if prior is not None:
                if prior.payload_hash == fingerprint and prior.target_id is not None:
                    replayed += 1
                else:
                    quarantined += 1
                    reasons["SOURCE_KEY_CONFLICT"] += 1
                continue
            reviewer = session.scalar(
                select(User)
                .join(RoleAssignment, RoleAssignment.user_id == User.id)
                .where(
                    User.id == item.reviewer_id,
                    User.organization_id == manifest.target_organization_id,
                    User.status == UserStatus.ACTIVE,
                    RoleAssignment.organization_id == manifest.target_organization_id,
                    RoleAssignment.role == Role.REVIEWER,
                )
            )
            task = session.scalar(
                select(TaskVersion)
                .join(TaskDefinition, TaskDefinition.id == TaskVersion.task_definition_id)
                .where(
                    TaskVersion.id == item.task_version_id,
                    TaskVersion.organization_id == manifest.target_organization_id,
                    TaskDefinition.organization_id == manifest.target_organization_id,
                    TaskDefinition.status == TaskDefinitionStatus.PUBLISHED,
                )
            )
            if reviewer is None or task is None:
                quarantined += 1
                reasons["OBJECT_SCOPE_CONFLICT"] += 1
            else:
                would_import += 1
    return safe_report(
        package_checksum=package_checksum,
        status="DRY_RUN_WITH_QUARANTINE" if quarantined else "DRY_RUN_CLEAN",
        record_count=len(records),
        imported_count=0,
        replayed_count=replayed,
        quarantined_count=quarantined,
        reasons=reasons,
        package_replay=False,
        mode="DRY_RUN",
        would_import_count=would_import,
    )


def apply_package(package_dir: Path) -> dict[str, object]:
    manifest, records, package_checksum = verify_package(package_dir)
    with SessionLocal.begin() as session:
        organization = session.get(Organization, manifest.target_organization_id)
        operator = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(
                User.id == manifest.operator_id,
                User.organization_id == manifest.target_organization_id,
                User.status == UserStatus.ACTIVE,
                RoleAssignment.organization_id == manifest.target_organization_id,
                RoleAssignment.role == Role.OPERATOR,
            )
        )
        if organization is None or operator is None:
            raise PackageError("package target organization or operator scope is invalid")
        session.scalar(select(User.id).where(User.id == operator.id).with_for_update())
        existing_batch = session.scalar(
            select(ImportBatch).where(ImportBatch.package_id == manifest.package_id)
        )
        if existing_batch is not None:
            if existing_batch.package_checksum != package_checksum:
                raise PackageError("package id was reused with different signed content")
            reasons = Counter(
                session.scalars(
                    select(ImportRecord.reason_code).where(
                        ImportRecord.batch_id == existing_batch.id,
                        ImportRecord.reason_code.is_not(None),
                    )
                ).all()
            )
            return safe_report(
                package_checksum=package_checksum,
                status=existing_batch.status,
                record_count=existing_batch.record_count,
                imported_count=0,
                replayed_count=existing_batch.imported_count + existing_batch.replayed_count,
                quarantined_count=existing_batch.quarantined_count,
                reasons=reasons,
                package_replay=True,
                mode="APPLY",
            )

        batch_id = uuid.uuid4()
        import_rows: list[ImportRecord] = []
        imported = 0
        replayed = 0
        quarantined = 0
        reasons: Counter[str] = Counter()
        for item in records:
            fingerprint = record_hash(item)
            prior = session.scalar(
                select(ImportRecord)
                .where(
                    ImportRecord.organization_id == manifest.target_organization_id,
                    ImportRecord.source_namespace == manifest.source_kind,
                    ImportRecord.source_key == item.source_key,
                    ImportRecord.status.in_(["IMPORTED", "REPLAYED"]),
                )
                .order_by(ImportRecord.created_at.desc(), ImportRecord.id)
            )
            status = "IMPORTED"
            reason_code: str | None = None
            target_id: uuid.UUID | None = None
            if prior is not None:
                if prior.payload_hash == fingerprint and prior.target_id is not None:
                    status = "REPLAYED"
                    target_id = prior.target_id
                    replayed += 1
                else:
                    status = "QUARANTINED"
                    reason_code = "SOURCE_KEY_CONFLICT"
            else:
                reviewer = session.scalar(
                    select(User)
                    .join(RoleAssignment, RoleAssignment.user_id == User.id)
                    .where(
                        User.id == item.reviewer_id,
                        User.organization_id == manifest.target_organization_id,
                        User.status == UserStatus.ACTIVE,
                        RoleAssignment.organization_id == manifest.target_organization_id,
                        RoleAssignment.role == Role.REVIEWER,
                    )
                )
                task = session.scalar(
                    select(TaskVersion)
                    .join(TaskDefinition, TaskDefinition.id == TaskVersion.task_definition_id)
                    .where(
                        TaskVersion.id == item.task_version_id,
                        TaskVersion.organization_id == manifest.target_organization_id,
                        TaskDefinition.organization_id == manifest.target_organization_id,
                        TaskDefinition.status == TaskDefinitionStatus.PUBLISHED,
                    )
                )
                if reviewer is None or task is None:
                    status = "QUARANTINED"
                    reason_code = "OBJECT_SCOPE_CONFLICT"
                else:
                    learner_id = uuid.uuid4()
                    enrollment_id = uuid.uuid4()
                    target_id = enrollment_id
                    session.add(
                        User(
                            id=learner_id,
                            organization_id=manifest.target_organization_id,
                            display_name=item.learner_display_name,
                            status=UserStatus.ACTIVE,
                        )
                    )
                    session.flush()
                    session.add(
                        RoleAssignment(
                            id=uuid.uuid4(),
                            organization_id=manifest.target_organization_id,
                            user_id=learner_id,
                            role=Role.LEARNER,
                        )
                    )
                    session.flush()
                    session.add(
                        Enrollment(
                            id=enrollment_id,
                            organization_id=manifest.target_organization_id,
                            learner_id=learner_id,
                            reviewer_id=item.reviewer_id,
                            status=EnrollmentStatus.ACTIVE,
                            revision=1,
                        )
                    )
                    session.flush()
                    session.add(
                        Assignment(
                            id=uuid.uuid4(),
                            organization_id=manifest.target_organization_id,
                            enrollment_id=enrollment_id,
                            task_definition_id=task.task_definition_id,
                            task_version_id=task.id,
                            position=1,
                            status=AssignmentStatus.AVAILABLE,
                            revision=1,
                        )
                    )
                    imported += 1
            if status == "QUARANTINED":
                quarantined += 1
                assert reason_code is not None
                reasons[reason_code] += 1
            import_rows.append(
                ImportRecord(
                    id=uuid.uuid4(),
                    batch_id=batch_id,
                    organization_id=manifest.target_organization_id,
                    source_namespace=manifest.source_kind,
                    source_key=item.source_key,
                    payload_hash=fingerprint,
                    target_type="enrollment",
                    target_id=target_id,
                    status=status,
                    reason_code=reason_code,
                )
            )
        batch_status = "APPLIED_WITH_QUARANTINE" if quarantined else "APPLIED"
        batch = ImportBatch(
            id=batch_id,
            organization_id=manifest.target_organization_id,
            package_id=manifest.package_id,
            package_checksum=package_checksum,
            source_revision=manifest.source_revision,
            schema_version=manifest.schema_version,
            status=batch_status,
            record_count=len(records),
            imported_count=imported,
            replayed_count=replayed,
            quarantined_count=quarantined,
            created_by=operator.id,
        )
        session.add(batch)
        session.add_all(import_rows)
        session.add(
            AuditEntry(
                id=uuid.uuid4(),
                organization_id=manifest.target_organization_id,
                actor_id=operator.id,
                action="offline_import.applied",
                resource_type="import_batch",
                resource_id=batch_id,
                result="SUCCESS",
                request_id=f"import_{package_checksum[:24]}",
                details={
                    "status": batch_status,
                    "record_count": len(records),
                    "imported_count": imported,
                    "replayed_count": replayed,
                    "quarantined_count": quarantined,
                },
            )
        )
        session.add(
            OutboxEvent(
                id=uuid.uuid4(),
                organization_id=manifest.target_organization_id,
                owner_id=operator.id,
                actor_id=operator.id,
                request_id=f"import_{package_checksum[:24]}",
                payload_version=1,
                event_type="offline_import.applied.v1",
                aggregate_type="import_batch",
                aggregate_id=batch_id,
                payload={"import_batch_id": str(batch_id)},
                status=OutboxStatus.PENDING,
            )
        )
    return safe_report(
        package_checksum=package_checksum,
        status=batch_status,
        record_count=len(records),
        imported_count=imported,
        replayed_count=replayed,
        quarantined_count=quarantined,
        reasons=reasons,
        package_replay=False,
        mode="APPLY",
    )


def write_secure(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def create_fixture_package(output_dir: Path) -> dict[str, object]:
    settings = get_settings()
    if settings.app_env not in {"local", "test"}:
        raise PackageError("fixture package creation is disabled outside local/test")
    if output_dir.exists():
        raise PackageError("fixture output directory must not already exist")
    with SessionLocal() as session:
        operator = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(
                User.status == UserStatus.ACTIVE,
                RoleAssignment.role == Role.OPERATOR,
                RoleAssignment.organization_id == User.organization_id,
            )
            .order_by(User.id)
        )
        if operator is None:
            raise PackageError("local fixture organization is incomplete")
        reviewer = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(
                User.organization_id == operator.organization_id,
                User.status == UserStatus.ACTIVE,
                RoleAssignment.role == Role.REVIEWER,
                RoleAssignment.organization_id == operator.organization_id,
            )
            .order_by(User.id)
        )
        task = session.scalar(
            select(TaskVersion)
            .join(TaskDefinition, TaskDefinition.id == TaskVersion.task_definition_id)
            .where(
                TaskDefinition.status == TaskDefinitionStatus.PUBLISHED,
                TaskDefinition.organization_id == operator.organization_id,
                TaskVersion.organization_id == operator.organization_id,
            )
            .order_by(TaskVersion.version.desc())
        )
        if reviewer is None or task is None:
            raise PackageError("local fixture organization is incomplete")
        if not (operator.organization_id == reviewer.organization_id == task.organization_id):
            raise PackageError("local fixture scope is inconsistent")
        package_id = uuid.uuid4()
        manifest = ImportManifest(
            schema_version=1,
            package_id=package_id,
            source_kind="SYNTHETIC_VNEXT_FIXTURE",
            source_revision=f"wp06-local-{package_id.hex[:12]}",
            created_at=datetime.now(UTC),
            target_environment=settings.app_env,
            target_organization_id=operator.organization_id,
            operator_id=operator.id,
            record_count=1,
            data_file=DATA_PATH,
        )
        record = EnrollmentImportRecord(
            source_key=f"wp06-synthetic:{package_id.hex}",
            learner_display_name="WP-06 合成导入新人",
            reviewer_id=reviewer.id,
            task_version_id=task.id,
        )
    manifest_bytes = canonical_json(manifest.model_dump(mode="json"))
    data_bytes = canonical_json(record.model_dump(mode="json")) + b"\n"
    checksum_bytes = f"{hashlib.sha256(data_bytes).hexdigest()}  {DATA_PATH}\n".encode()
    signature = hmac.new(
        settings.import_signing_key.encode(),
        manifest_bytes + b"\n" + checksum_bytes,
        hashlib.sha256,
    ).hexdigest().encode() + b"\n"
    output_dir.mkdir(mode=0o700, parents=True)
    (output_dir / "data").mkdir(mode=0o700)
    write_secure(output_dir / "manifest.json", manifest_bytes)
    write_secure(output_dir / "checksums.sha256", checksum_bytes)
    write_secure(output_dir / "signature", signature)
    write_secure(output_dir / DATA_PATH, data_bytes)
    return {
        "contract": "journey-next-offline-import-v1",
        "status": "SIGNED_LOCAL_FIXTURE_CREATED",
        "record_count": 1,
        "contains_real_business_data": False,
    }


def write_report(path: Path, report: dict[str, object]) -> None:
    if path.exists():
        raise PackageError("report path already exists")
    write_secure(path, json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and apply a signed offline import package")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create-fixture")
    create_parser.add_argument("package_dir", type=Path)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("package_dir", type=Path)
    apply_parser.add_argument("--report", type=Path)
    dry_run_parser = subparsers.add_parser("dry-run")
    dry_run_parser.add_argument("package_dir", type=Path)
    dry_run_parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create-fixture":
            result = create_fixture_package(args.package_dir)
        elif args.command == "dry-run":
            result = dry_run_package(args.package_dir)
            if args.report is not None:
                write_report(args.report, result)
        else:
            result = apply_package(args.package_dir)
            if args.report is not None:
                write_report(args.report, result)
    except PackageError as exc:
        parser.exit(2, f"offline import rejected: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
