#!/usr/bin/env python3
"""Generate and verify the small, SHA-bound WP-07 release manifest."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("api", "web", "worker")
FULL_SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
MANIFEST_SCHEMA_VERSION = 2
ALEMBIC_REVISION_MAX_LENGTH = 32
GHCR_PREFIX = "ghcr.io/muchenai2024-creator/muchen-journey-vnext"
TRACE_IDS = (
    "ISO-MUST-001",
    "ISO-MUST-002",
    "ISO-MUST-008",
    "REQ-NFR-001",
    "REQ-NFR-010",
    "AT-ISO-001",
    "AT-ARCH-005",
    "AT-ARCH-007",
)
LOCAL_EXTERNAL_STATUS = {
    "protected_main": "NOT_RUN",
    "registry_push": "NOT_RUN",
    "deployment": "NOT_RUN",
}
REGISTRY_EXTERNAL_STATUS = {
    "protected_main": "NOT_RUN",
    "registry_push": "VERIFIED",
    "deployment": "NOT_RUN",
}


class CandidateError(RuntimeError):
    pass


def run(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        list(arguments),
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        raise CandidateError(result.stderr.strip() or result.stdout.strip() or "command failed")
    return result.stdout.strip()


def run_bytes(arguments: Sequence[str]) -> bytes:
    result = subprocess.run(
        list(arguments),
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        message = result.stderr.decode(errors="replace").strip() or "command failed"
        raise CandidateError(message)
    return result.stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_artifact(value: str | Path, *, label: str, require_relative: bool) -> Path:
    if not isinstance(value, (str, Path)):
        raise CandidateError(f"{label} path is invalid")
    raw = Path(value)
    if require_relative and raw.is_absolute():
        raise CandidateError(f"{label} path must be repository-relative")
    path = (ROOT / raw).resolve() if not raw.is_absolute() else raw.resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise CandidateError(f"{label} path must resolve to a repository file")
    return path


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def git_sha(*, clean: bool) -> str:
    value = run(("git", "rev-parse", "--verify", "HEAD"))
    if not FULL_SHA.fullmatch(value):
        raise CandidateError("candidate requires a full 40-character Git HEAD")
    if clean:
        status = run(("git", "status", "--porcelain=v1", "--untracked-files=all"))
        if status:
            raise CandidateError("candidate worktree has staged, modified, or untracked source files")
    return value


def assignments(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for node in ast.parse(path.read_text(encoding="utf-8"), filename=str(path)).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return result


def migration() -> dict[str, Any]:
    revisions: dict[str, str | None] = {}
    for path in sorted((ROOT / "migrations" / "versions").glob("*.py")):
        values = assignments(path)
        revision, parent = values.get("revision"), values.get("down_revision")
        if not isinstance(revision, str) or (parent is not None and not isinstance(parent, str)):
            raise CandidateError(f"migration metadata must be literal and linear: {path.name}")
        if not revision or len(revision) > ALEMBIC_REVISION_MAX_LENGTH:
            raise CandidateError(
                f"migration revision must be 1-{ALEMBIC_REVISION_MAX_LENGTH} characters: {path.name}"
            )
        if revision in revisions:
            raise CandidateError(f"duplicate migration revision: {revision}")
        revisions[revision] = parent
    roots = [item for item, parent in revisions.items() if parent is None]
    heads = [item for item in revisions if item not in {parent for parent in revisions.values()}]
    if roots != ["0001_initial"] or len(heads) != 1:
        raise CandidateError(f"migration chain must have root 0001_initial and one head: {roots}, {heads}")
    seen: set[str] = set()
    cursor: str | None = heads[0]
    while cursor:
        if cursor in seen or cursor not in revisions:
            raise CandidateError(f"migration chain is cyclic or disconnected at {cursor}")
        seen.add(cursor)
        cursor = revisions[cursor]
    if seen != set(revisions):
        raise CandidateError("migration chain contains disconnected revisions")
    return {"root": roots[0], "head": heads[0], "revision_count": len(revisions)}


def config_schema() -> int:
    path = ROOT / "apps" / "api" / "journey_api" / "config.py"
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "config_schema_version"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, int)
        ):
            return node.value.value
    raise CandidateError("config schema version must be a literal integer")


def source_check() -> dict[str, Any]:
    for relative in (
        ".github/CODEOWNERS",
        ".github/workflows/ci.yml",
        ".github/workflows/mainline.yml",
        "Makefile",
        "scripts/check_isolation.sh",
        "contracts/openapi.json",
        "requirements.lock",
        "apps/web/package-lock.json",
    ):
        if not (ROOT / relative).is_file():
            raise CandidateError(f"missing WP-07 source contract: {relative}")
    workflows = [
        (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        for name in ("ci.yml", "mainline.yml")
    ]
    for workflow in workflows:
        action_refs = re.findall(r"uses:\s+[^@\s]+@([^\s#]+)", workflow)
        if not action_refs or any(not FULL_SHA.fullmatch(ref) for ref in action_refs):
            raise CandidateError("GitHub Actions must be pinned to full commit SHAs")
    mainline = workflows[1]
    required_mainline = (
        "permissions:\n  contents: read\n  packages: write",
        "docker/login-action@4907a6ddec9925e35a0a9e82d7399ccc52663121",
        "password: ${{ secrets.GITHUB_TOKEN }}",
        "make candidate-registry-push",
    )
    if any(item not in mainline for item in required_mainline) or ":latest" in mainline:
        raise CandidateError("mainline GHCR workflow contract is invalid")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    http_negative = re.search(
        r"(?m)^http-negative-check:\n((?:\t[^\n]*\n)+)", makefile
    )
    required_http_negative = (
        "\tMJ_DB_PORT=$${MJ_DB_PORT:-$(WP08_LOCAL_DB_PORT)} "
        "MJ_API_PORT=$${MJ_API_PORT:-$(WP08_LOCAL_API_PORT)} "
        "docker compose up --build -d --wait db api\n"
        "\tMJ_API_PORT=$${MJ_API_PORT:-$(WP08_LOCAL_API_PORT)} "
        "python3 scripts/wp06_ops.py http-negative\n"
    )
    if http_negative is None or http_negative.group(1) != required_http_negative:
        raise CandidateError("HTTP negative gate must self-start only db and api")
    openapi = json.loads((ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8"))
    if openapi.get("openapi") != "3.1.0" or not openapi.get("paths"):
        raise CandidateError("OpenAPI contract is invalid or empty")
    evidence = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "docs").glob("*.md")
        if path.name in {
            "02_GREENFIELD_CHARTER_AND_ISOLATION_CONTRACT.md",
            "06_SYSTEM_ARCHITECTURE_AND_ADRS.md",
            "13_REQUIREMENTS_TRACEABILITY_MATRIX.md",
            "23_G4_G6_NEXT_WORK_PACKAGES.md",
        }
    )
    missing = [item for item in TRACE_IDS if item not in evidence]
    if missing:
        raise CandidateError(f"missing WP-07 trace IDs: {missing}")
    return {
        "openapi_sha256": sha256(ROOT / "contracts" / "openapi.json"),
        "migration": migration(),
        "config_schema_version": config_schema(),
        "trace_ids": list(TRACE_IDS),
    }


def task_versions() -> list[dict[str, Any]]:
    try:
        from sqlalchemy import select
        from journey_api.db import SessionLocal
        from journey_api.models import TaskDefinition, TaskVersion
    except ImportError as error:
        raise CandidateError("task-versions must run in the API container") from error
    items: list[dict[str, Any]] = []
    with SessionLocal() as session:
        rows = session.execute(
            select(TaskDefinition.stable_key, TaskVersion)
            .join(TaskVersion, TaskVersion.task_definition_id == TaskDefinition.id)
            .order_by(TaskDefinition.stable_key, TaskVersion.version)
        ).all()
        for stable_key, version in rows:
            content = {
                "title": version.title,
                "instructions": version.instructions,
                "completion_criteria": version.completion_criteria,
                "rubric": version.rubric,
                "allowed_attachment_types": version.allowed_attachment_types,
                "max_attachment_size_bytes": version.max_attachment_size_bytes,
            }
            items.append(
                {
                    "stable_key": stable_key,
                    "version": version.version,
                    "task_version_id": str(version.id),
                    "content_sha256": hashlib.sha256(
                        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                }
            )
    if not items:
        raise CandidateError("candidate database contains no TaskVersion")
    return items


def mapping(values: Iterable[str]) -> dict[str, str]:
    result = dict(value.split("=", 1) for value in values if "=" in value)
    if set(result) != set(COMPONENTS):
        raise CandidateError(f"expected exactly these components: {COMPONENTS}")
    return result


def canonical_registry_references(commit: str) -> dict[str, str]:
    if not FULL_SHA.fullmatch(commit):
        raise CandidateError("registry images require a full 40-character commit tag")
    return {component: f"{GHCR_PREFIX}-{component}:{commit}" for component in COMPONENTS}


def registry_mapping(commit: str, values: Iterable[str]) -> dict[str, str]:
    references = mapping(values)
    if references != canonical_registry_references(commit):
        raise CandidateError("registry images must use the canonical GHCR repositories and commit tag")
    return references


def remote_manifest_digest(reference: str) -> str:
    raw = run_bytes(("docker", "buildx", "imagetools", "inspect", "--raw", reference))
    manifest = json.loads(raw)
    if manifest.get("schemaVersion") != 2:
        raise CandidateError(f"remote registry returned an invalid image manifest: {reference}")
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    repository = reference.rsplit(":", 1)[0]
    immutable = f"{repository}@{digest}"
    immutable_raw = run_bytes(
        ("docker", "buildx", "imagetools", "inspect", "--raw", immutable)
    )
    if "sha256:" + hashlib.sha256(immutable_raw).hexdigest() != digest:
        raise CandidateError(f"remote registry digest verification failed: {reference}")
    return digest


def registry_check(commit: str, registry_args: Iterable[str]) -> dict[str, Any]:
    references = registry_mapping(commit, registry_args)
    return {
        "candidate_sha": commit,
        "registry_images": references,
        "registry_push": "NOT_RUN",
    }


def generate(task_path: Path, image_args: Iterable[str], sbom_args: Iterable[str]) -> dict[str, Any]:
    commit = git_sha(clean=True)
    images, sboms = mapping(image_args), mapping(sbom_args)
    image_manifest: dict[str, Any] = {}
    for component in COMPONENTS:
        inspected = json.loads(run(("docker", "image", "inspect", images[component])))[0]
        labels = inspected.get("Config", {}).get("Labels") or {}
        if labels.get("org.opencontainers.image.revision") != commit:
            raise CandidateError(f"{component} image does not carry candidate revision")
        sbom_path = repository_artifact(
            sboms[component], label=f"{component} SBOM", require_relative=False
        )
        if not str(json.loads(sbom_path.read_text())["spdxVersion"]).startswith("SPDX-"):
            raise CandidateError(f"{component} SBOM is not SPDX JSON")
        image_manifest[component] = {
            "reference": images[component],
            "local_image_digest": inspected["Id"],
            "registry_reference": None,
            "registry_digest": None,
            "revision_label": commit,
            "sbom": {
                "format": "SPDX-JSON",
                "path": str(sbom_path.relative_to(ROOT)),
                "sha256": sha256(sbom_path),
            },
        }
    task_path = repository_artifact(task_path, label="TaskVersion artifact", require_relative=False)
    tasks = json.loads(task_path.read_text(encoding="utf-8"))
    if not isinstance(tasks, list) or not tasks:
        raise CandidateError("TaskVersion list is empty")
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "candidate": {
            "commit_sha": commit,
            "branch": run(("git", "branch", "--show-current")),
            "repository": run(("git", "remote", "get-url", "origin")),
            "source_tree_clean": True,
        },
        "build": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "builder": os.environ.get("GITHUB_ACTOR") or run(("git", "config", "--get", "user.name")),
        },
        "openapi": {"path": "contracts/openapi.json", "sha256": source_check()["openapi_sha256"]},
        "migration": migration(),
        "config_schema_version": config_schema(),
        "task_versions": tasks,
        "task_versions_artifact": {
            "path": str(task_path.relative_to(ROOT)),
            "sha256": sha256(task_path),
        },
        "images": image_manifest,
        "external_status": LOCAL_EXTERNAL_STATUS,
    }


def promote_registry(path: Path, registry_args: Iterable[str]) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("external_status") != LOCAL_EXTERNAL_STATUS:
        raise CandidateError("registry promotion requires a locally verified NOT_RUN manifest")
    verify(path)
    commit = value.get("candidate", {}).get("commit_sha", "")
    references = registry_mapping(commit, registry_args)
    digests = {
        component: remote_manifest_digest(references[component]) for component in COMPONENTS
    }
    for component in COMPONENTS:
        value["images"][component]["registry_reference"] = references[component]
        value["images"][component]["registry_digest"] = digests[component]
    value["external_status"] = REGISTRY_EXTERNAL_STATUS
    write_json(path, value)
    return verify(path)


def verify(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    commit = git_sha(clean=True)
    if value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise CandidateError("manifest schema version is invalid")
    if value.get("candidate", {}).get("commit_sha") != commit:
        raise CandidateError("manifest commit does not match HEAD")
    if value.get("openapi", {}).get("sha256") != sha256(ROOT / "contracts" / "openapi.json"):
        raise CandidateError("manifest OpenAPI hash drifted")
    if value.get("migration") != migration() or value.get("config_schema_version") != config_schema():
        raise CandidateError("manifest migration/config drifted")
    external_status = value.get("external_status")
    if external_status == LOCAL_EXTERNAL_STATUS:
        registry_verified = False
    elif external_status == REGISTRY_EXTERNAL_STATUS:
        registry_verified = True
    else:
        raise CandidateError("manifest external status is not an allowed exact state")
    canonical_references = canonical_registry_references(commit)
    images = value.get("images")
    if not isinstance(images, dict) or set(images) != set(COMPONENTS):
        raise CandidateError("manifest must contain exactly the API/Web/Worker images")
    task_evidence = value.get("task_versions_artifact")
    if not isinstance(task_evidence, dict):
        raise CandidateError("manifest TaskVersion artifact entry is invalid")
    task_path = repository_artifact(
        task_evidence.get("path", ""), label="TaskVersion artifact", require_relative=True
    )
    tasks = json.loads(task_path.read_text(encoding="utf-8"))
    if (
        not isinstance(tasks, list)
        or not tasks
        or task_evidence.get("sha256") != sha256(task_path)
        or value.get("task_versions") != tasks
    ):
        raise CandidateError("manifest TaskVersion artifact hash/content drifted")
    for component in COMPONENTS:
        item = images[component]
        if not isinstance(item, dict):
            raise CandidateError(f"manifest image entry is invalid: {component}")
        reference = item.get("reference")
        sbom = item.get("sbom")
        if not isinstance(reference, str) or not isinstance(sbom, dict):
            raise CandidateError(f"manifest image/SBOM entry is invalid: {component}")
        if "registry_reference" not in item or "registry_digest" not in item:
            raise CandidateError(f"manifest registry entry is incomplete: {component}")
        sbom_path = repository_artifact(
            sbom.get("path", ""), label=f"{component} SBOM", require_relative=True
        )
        inspected = json.loads(run(("docker", "image", "inspect", reference)))[0]
        labels = inspected.get("Config", {}).get("Labels") or {}
        if (
            item.get("local_image_digest") != inspected.get("Id")
            or item.get("revision_label") != labels.get("org.opencontainers.image.revision")
            or item.get("revision_label") != commit
            or not str(json.loads(sbom_path.read_text())["spdxVersion"]).startswith("SPDX-")
            or sbom.get("sha256") != sha256(sbom_path)
        ):
            raise CandidateError(f"manifest image/SBOM drifted: {component}")
        registry_reference = item.get("registry_reference")
        registry_digest = item.get("registry_digest")
        if not registry_verified:
            if registry_reference is not None or registry_digest is not None:
                raise CandidateError(f"local manifest contains registry evidence: {component}")
        elif (
            registry_reference != canonical_references[component]
            or not isinstance(registry_digest, str)
            or not DIGEST.fullmatch(registry_digest)
            or remote_manifest_digest(registry_reference) != registry_digest
        ):
            raise CandidateError(f"remote registry evidence is invalid: {component}")
    return {"candidate_sha": commit, "manifest_sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    commands.add_parser("preflight")
    registry_contract = commands.add_parser("registry-check")
    registry_contract.add_argument("--commit", required=True)
    registry_contract.add_argument("--registry-image", action="append", default=[])
    tasks = commands.add_parser("task-versions")
    tasks.add_argument("--output", type=Path, required=True)
    manifest = commands.add_parser("generate")
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("--task-versions", type=Path, required=True)
    manifest.add_argument("--image", action="append", default=[])
    manifest.add_argument("--sbom", action="append", default=[])
    verification = commands.add_parser("verify")
    verification.add_argument("path", type=Path)
    registry = commands.add_parser("registry")
    registry.add_argument("--manifest", type=Path, required=True)
    registry.add_argument("--registry-image", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.command == "check":
            result = source_check()
        elif args.command == "preflight":
            result = {"candidate_sha": git_sha(clean=True), **source_check()}
        elif args.command == "registry-check":
            result = registry_check(args.commit, args.registry_image)
        elif args.command == "task-versions":
            result = task_versions()
            write_json(args.output, result)
        elif args.command == "generate":
            result = generate(args.task_versions, args.image, args.sbom)
            write_json(args.output, result)
        elif args.command == "verify":
            result = verify(args.path)
        else:
            result = promote_registry(args.manifest, args.registry_image)
    except (CandidateError, FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"WP-07 candidate check failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
