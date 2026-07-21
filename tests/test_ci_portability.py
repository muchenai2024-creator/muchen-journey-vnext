import os
import shutil
import subprocess
from pathlib import Path


SOURCE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_isolation.sh"
RUNTIME_COMMANDS = ("dirname", "grep", "find", "sort", "head", "basename")


def isolation_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copyfile(SOURCE_SCRIPT, root / "scripts" / "check_isolation.sh")
    (root / "apps").mkdir()
    (root / "migrations" / "versions").mkdir(parents=True)
    (root / "migrations" / "versions" / "0001_initial.py").write_text(
        "revision = '0001_initial'\n", encoding="utf-8"
    )
    for relative in ("compose.yaml", "Makefile", "pyproject.toml", "requirements.lock"):
        (root / relative).write_text("# clean\n", encoding="utf-8")
    return root


def path_without_rg(
    tmp_path: Path, *, include_grep: bool = True, broken_grep: bool = False
) -> str:
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    for command in RUNTIME_COMMANDS:
        if command == "grep" and not include_grep:
            continue
        source = shutil.which(command)
        assert source is not None
        destination = binary_dir / command
        if command == "grep" and broken_grep:
            destination.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
            destination.chmod(0o755)
        else:
            destination.symlink_to(source)
    assert shutil.which("rg", path=str(binary_dir)) is None
    return str(binary_dir)


def run_isolation(root: Path, path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", str(root / "scripts" / "check_isolation.sh")],
        cwd=root,
        env={**os.environ, "PATH": path},
        check=False,
        capture_output=True,
        text=True,
    )


def test_isolation_grep_fallback_passes_clean_and_rejects_forbidden_reference(tmp_path):
    root = isolation_tree(tmp_path)
    path = path_without_rg(tmp_path)

    clean = run_isolation(root, path)
    assert clean.returncode == 0, clean.stderr
    assert "isolation checks passed" in clean.stdout

    (root / "apps" / "runtime.txt").write_text("journey_p0\n", encoding="utf-8")
    forbidden = run_isolation(root, path)
    assert forbidden.returncode != 0
    assert "forbidden old-system reference found" in forbidden.stdout


def test_isolation_scanner_execution_error_fails_closed(tmp_path):
    root = isolation_tree(tmp_path)
    result = run_isolation(root, path_without_rg(tmp_path, broken_grep=True))

    assert result.returncode == 2
    assert "scanner execution failed with status 2" in result.stderr


def test_isolation_without_supported_scanner_fails_closed(tmp_path):
    root = isolation_tree(tmp_path)
    result = run_isolation(root, path_without_rg(tmp_path, include_grep=False))

    assert result.returncode == 2
    assert "neither rg nor grep is available" in result.stderr
