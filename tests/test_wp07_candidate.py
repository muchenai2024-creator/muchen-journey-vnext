import json

import pytest

import scripts.wp07_candidate as candidate
from scripts.wp07_candidate import ROOT, CandidateError, config_schema, migration


FULL_SHA = "a" * 40
REMOTE_DIGEST = "sha256:" + "b" * 64


@pytest.fixture
def candidate_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate, "ROOT", tmp_path)
    monkeypatch.setattr(candidate, "git_sha", lambda *, clean: FULL_SHA)
    expected_migration = {
        "root": "0001_initial",
        "head": "0010_wp06_governance",
        "revision_count": 10,
    }
    monkeypatch.setattr(candidate, "migration", lambda: expected_migration)
    monkeypatch.setattr(candidate, "config_schema", lambda: 1)
    monkeypatch.setattr(candidate, "remote_manifest_digest", lambda reference: REMOTE_DIGEST)

    contract_path = tmp_path / "contracts" / "openapi.json"
    contract_path.parent.mkdir()
    contract_path.write_text("{}\n", encoding="utf-8")

    task_versions = [{"stable_key": "TSK-001", "version": 1, "content_sha256": "1" * 64}]
    task_path = tmp_path / "artifacts" / "task-versions.json"
    task_path.parent.mkdir()
    task_path.write_text(json.dumps(task_versions), encoding="utf-8")

    images = {}
    image_digests = {}
    for component in candidate.COMPONENTS:
        sbom_path = tmp_path / "artifacts" / f"{component}.spdx.json"
        sbom_path.write_text(json.dumps({"spdxVersion": "SPDX-2.3"}), encoding="utf-8")
        image_digest = "sha256:" + candidate.hashlib.sha256(component.encode()).hexdigest()
        image_digests[component] = image_digest
        images[component] = {
            "reference": f"candidate-{component}:{FULL_SHA}",
            "local_image_digest": image_digest,
            "registry_reference": None,
            "registry_digest": None,
            "revision_label": FULL_SHA,
            "sbom": {
                "format": "SPDX-JSON",
                "path": str(sbom_path.relative_to(tmp_path)),
                "sha256": candidate.sha256(sbom_path),
            },
        }

    def inspect_image(arguments):
        reference = arguments[-1]
        component = next(item for item in candidate.COMPONENTS if f"-{item}:" in reference)
        return json.dumps(
            [
                {
                    "Id": image_digests[component],
                    "Config": {"Labels": {"org.opencontainers.image.revision": FULL_SHA}},
                }
            ]
        )

    monkeypatch.setattr(candidate, "run", inspect_image)
    manifest = {
        "schema_version": candidate.MANIFEST_SCHEMA_VERSION,
        "candidate": {"commit_sha": FULL_SHA},
        "openapi": {"sha256": candidate.sha256(contract_path)},
        "migration": expected_migration,
        "config_schema_version": 1,
        "task_versions": task_versions,
        "task_versions_artifact": {
            "path": str(task_path.relative_to(tmp_path)),
            "sha256": candidate.sha256(task_path),
        },
        "images": images,
        "external_status": dict(candidate.LOCAL_EXTERNAL_STATUS),
    }
    manifest_path = tmp_path / "artifacts" / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, task_path, manifest


def test_wp07_manifest_inputs_match_candidate_contract():
    assert migration() == {
        "root": "0001_initial",
        "head": "0010_wp06_governance",
        "revision_count": 10,
    }
    assert config_schema() == 1
    assert (ROOT / "contracts" / "openapi.json").is_file()


def test_manifest_inputs_are_literal_and_linear():
    assert migration()["head"] == "0010_wp06_governance"
    assert config_schema() == 1


def test_verify_accepts_bound_task_artifact_and_not_run_status(candidate_manifest):
    manifest_path, _, _ = candidate_manifest

    assert candidate.verify(manifest_path)["candidate_sha"] == FULL_SHA


def test_verify_accepts_canonical_remote_registry_evidence(candidate_manifest):
    manifest_path, _, manifest = candidate_manifest
    manifest["external_status"] = dict(candidate.REGISTRY_EXTERNAL_STATUS)
    for component, reference in candidate.canonical_registry_references(FULL_SHA).items():
        manifest["images"][component]["registry_reference"] = reference
        manifest["images"][component]["registry_digest"] = REMOTE_DIGEST
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert candidate.verify(manifest_path)["candidate_sha"] == FULL_SHA


@pytest.mark.parametrize(
    "external_status",
    [
        {"protected_main": "PASS", "registry_push": "NOT_RUN", "deployment": "NOT_RUN"},
        {"protected_main": "NOT_RUN", "registry_push": "NOT_RUN"},
        {**candidate.LOCAL_EXTERNAL_STATUS, "remote_ci": "PASS"},
        {"protected_main": "NOT_RUN", "registry_push": "PASS", "deployment": "NOT_RUN"},
        {"protected_main": "VERIFIED", "registry_push": "VERIFIED", "deployment": "NOT_RUN"},
    ],
)
def test_verify_rejects_external_status_tampering(candidate_manifest, external_status):
    manifest_path, _, manifest = candidate_manifest
    manifest["external_status"] = external_status
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CandidateError, match="external status"):
        candidate.verify(manifest_path)


def test_verify_rejects_task_version_artifact_tampering(candidate_manifest):
    manifest_path, task_path, _ = candidate_manifest
    task_path.write_text(json.dumps([{"stable_key": "TSK-TAMPERED"}]), encoding="utf-8")

    with pytest.raises(CandidateError, match="hash/content drifted"):
        candidate.verify(manifest_path)


def test_verify_rejects_inline_task_version_tampering(candidate_manifest):
    manifest_path, _, manifest = candidate_manifest
    manifest["task_versions"][0]["content_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CandidateError, match="hash/content drifted"):
        candidate.verify(manifest_path)


def test_verify_rejects_task_version_path_escape(candidate_manifest):
    manifest_path, _, manifest = candidate_manifest
    manifest["task_versions_artifact"]["path"] = "../task-versions.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CandidateError, match="repository file"):
        candidate.verify(manifest_path)


def test_verify_rejects_registry_evidence_in_local_mode(candidate_manifest):
    manifest_path, _, manifest = candidate_manifest
    manifest["images"]["api"]["registry_reference"] = candidate.canonical_registry_references(
        FULL_SHA
    )["api"]
    manifest["images"]["api"]["registry_digest"] = REMOTE_DIGEST
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CandidateError, match="local manifest contains registry evidence"):
        candidate.verify(manifest_path)


@pytest.mark.parametrize(
    ("reference", "digest"),
    [
        (f"ghcr.io/other/muchen-journey-vnext-api:{FULL_SHA}", REMOTE_DIGEST),
        (f"{candidate.GHCR_PREFIX}-api:latest", REMOTE_DIGEST),
        (f"{candidate.GHCR_PREFIX}-api:{FULL_SHA}", "sha256:1234"),
        (f"{candidate.GHCR_PREFIX}-api:{FULL_SHA}", "sha256:" + "c" * 64),
        (f"{candidate.GHCR_PREFIX}-api:{FULL_SHA}", None),
    ],
)
def test_verify_rejects_noncanonical_or_invalid_registry_evidence(
    candidate_manifest, reference, digest
):
    manifest_path, _, manifest = candidate_manifest
    manifest["external_status"] = dict(candidate.REGISTRY_EXTERNAL_STATUS)
    for component, canonical in candidate.canonical_registry_references(FULL_SHA).items():
        manifest["images"][component]["registry_reference"] = canonical
        manifest["images"][component]["registry_digest"] = REMOTE_DIGEST
    manifest["images"]["api"]["registry_reference"] = reference
    manifest["images"]["api"]["registry_digest"] = digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CandidateError, match="remote registry evidence"):
        candidate.verify(manifest_path)


def test_verify_rejects_missing_registry_field(candidate_manifest):
    manifest_path, _, manifest = candidate_manifest
    del manifest["images"]["api"]["registry_digest"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CandidateError, match="registry entry is incomplete"):
        candidate.verify(manifest_path)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_verify_requires_exact_image_components(candidate_manifest, mutation):
    manifest_path, _, manifest = candidate_manifest
    if mutation == "missing":
        del manifest["images"]["worker"]
    else:
        manifest["images"]["db"] = dict(manifest["images"]["api"])
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CandidateError, match="exactly the API/Web/Worker"):
        candidate.verify(manifest_path)


def test_registry_check_requires_all_canonical_commit_tagged_images():
    references = candidate.canonical_registry_references(FULL_SHA)
    arguments = [f"{component}={reference}" for component, reference in references.items()]

    assert candidate.registry_check(FULL_SHA, arguments)["registry_push"] == "NOT_RUN"
    with pytest.raises(CandidateError, match="expected exactly"):
        candidate.registry_check(FULL_SHA, arguments[:-1])


def test_promote_registry_upgrades_only_a_valid_local_manifest(candidate_manifest):
    manifest_path, _, _ = candidate_manifest
    references = candidate.canonical_registry_references(FULL_SHA)
    arguments = [f"{component}={reference}" for component, reference in references.items()]

    candidate.promote_registry(manifest_path, arguments)
    promoted = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert promoted["external_status"] == candidate.REGISTRY_EXTERNAL_STATUS
    assert all(
        promoted["images"][component]["registry_reference"] == references[component]
        and promoted["images"][component]["registry_digest"] == REMOTE_DIGEST
        for component in candidate.COMPONENTS
    )


def test_remote_manifest_digest_rechecks_immutable_reference(monkeypatch):
    raw = b'{"schemaVersion":2,"mediaType":"application/vnd.oci.image.index.v1+json"}'
    expected = "sha256:" + candidate.hashlib.sha256(raw).hexdigest()
    calls = []

    def inspect(arguments):
        calls.append(arguments[-1])
        return raw

    monkeypatch.setattr(candidate, "run_bytes", inspect)

    assert candidate.remote_manifest_digest("ghcr.io/example/image:tag") == expected
    assert calls == ["ghcr.io/example/image:tag", f"ghcr.io/example/image@{expected}"]


def test_remote_manifest_digest_rejects_immutable_mismatch(monkeypatch):
    responses = iter(
        [
            b'{"schemaVersion":2,"mediaType":"application/vnd.oci.image.index.v1+json"}',
            b'{"schemaVersion":2,"tampered":true}',
        ]
    )
    monkeypatch.setattr(candidate, "run_bytes", lambda arguments: next(responses))

    with pytest.raises(CandidateError, match="digest verification failed"):
        candidate.remote_manifest_digest("ghcr.io/example/image:tag")
