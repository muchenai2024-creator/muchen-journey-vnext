import json

import pytest

import scripts.wp07_candidate as candidate
from scripts.wp07_candidate import ROOT, CandidateError, config_schema, migration


FULL_SHA = "a" * 40


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
        "external_status": dict(candidate.EXPECTED_EXTERNAL_STATUS),
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


@pytest.mark.parametrize(
    "external_status",
    [
        {"protected_main": "PASS", "registry_push": "NOT_RUN", "deployment": "NOT_RUN"},
        {"protected_main": "NOT_RUN", "registry_push": "NOT_RUN"},
        {**candidate.EXPECTED_EXTERNAL_STATUS, "remote_ci": "PASS"},
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
