import json
import os
from pathlib import Path

import pytest

import scripts.wp07_candidate as candidate
import scripts.wp08_readiness as readiness


def test_migration_rejects_duplicate_and_overlong_revisions(tmp_path, monkeypatch):
    versions = tmp_path / "migrations" / "versions"
    versions.mkdir(parents=True)
    (versions / "a.py").write_text('revision = "0001_initial"\ndown_revision = None\n')
    (versions / "b.py").write_text('revision = "0001_initial"\ndown_revision = "0001_initial"\n')
    monkeypatch.setattr(candidate, "ROOT", tmp_path)

    with pytest.raises(candidate.CandidateError, match="duplicate"):
        candidate.migration()

    (versions / "b.py").write_text(
        f'revision = "{"x" * 33}"\ndown_revision = "0001_initial"\n'
    )
    with pytest.raises(candidate.CandidateError, match="1-32"):
        candidate.migration()


def test_fixture_manifest_is_pii_free_and_stable(tmp_path):
    output = tmp_path / "fixture-manifest.json"
    manifest = readiness.fixture_manifest(output)

    assert manifest["classification"] == "SYNTHETIC_NO_REAL_PII"
    assert manifest["builder"] == "python -m journey_api.seed"
    assert "users" in manifest["tables"]
    assert "learner" in manifest["stable_references"]
    assert "试点新人" not in output.read_text(encoding="utf-8")


def test_browser_spec_is_pinned_and_complete():
    spec = readiness.browser_spec(readiness.DEFAULT_BROWSER_SPEC)

    assert spec["browser_revision"] == "1232"
    assert {item["name"] for item in spec["viewports"]} == {"desktop", "tablet", "mobile"}
    assert "focus_keyboard" in spec["checks"]


def test_browser_preflight_rejects_insecure_staging_url(tmp_path, monkeypatch):
    cli = tmp_path / "playwright_cli.sh"
    cli.write_text("#!/bin/sh\n")
    executable = tmp_path / "chromium-1232" / "chrome"
    executable.parent.mkdir()
    executable.write_text("binary")
    executable.chmod(0o700)
    monkeypatch.setattr(readiness.shutil, "which", lambda command: "/bin/npx")
    monkeypatch.setattr(
        readiness,
        "run",
        lambda arguments, check=True: readiness.subprocess.CompletedProcess(arguments, 0, "", ""),
    )
    monkeypatch.setenv("PLAYWRIGHT_CLI", str(cli))
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", str(executable))
    monkeypatch.setenv("BROWSER_SCOPE", "staging")
    monkeypatch.setenv("BROWSER_BASE_URL", "http://staging.example.test")

    with pytest.raises(readiness.ReadinessError, match="non-local HTTPS"):
        readiness.browser_preflight(readiness.DEFAULT_BROWSER_SPEC)


def test_private_evidence_boundary_is_0700_0600(tmp_path):
    root = tmp_path / "private"
    metadata = readiness.evidence_init(root, 90)
    result = readiness.evidence_check(root)

    assert result["status"] == "PASS"
    assert result["access_scope"] == "LOCAL_FILESYSTEM_OWNER_ONLY"
    assert os.stat(root).st_mode & 0o777 == 0o700
    assert os.stat(metadata).st_mode & 0o777 == 0o600
    assert "PEV-WP08" in json.loads(metadata.read_text())["public_reference_format"]


def test_private_evidence_rejects_unignored_public_repo_path(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(readiness, "ROOT", repo)
    monkeypatch.setattr(
        readiness,
        "run",
        lambda arguments, check=True: readiness.subprocess.CompletedProcess(arguments, 1, "", ""),
    )

    with pytest.raises(readiness.ReadinessError, match="Git-ignored"):
        readiness.private_root(repo / "public-evidence")


def test_private_evidence_rejects_symlink_root(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(readiness.ReadinessError, match="must not be a symlink"):
        readiness.evidence_init(link, 90)
