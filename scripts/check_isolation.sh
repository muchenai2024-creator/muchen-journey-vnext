#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"

if test -f .gitmodules; then
  echo "ISO-MUST-001 failed: submodules are forbidden"
  exit 1
fi

runtime_paths="apps migrations compose.yaml Makefile pyproject.toml requirements.lock"
forbidden='journey_p0|exploration_v2|exploration-camp/v2|frontend/lib/adapters|legacy redirect|0017_p0|Muchen Quest'
if rg -n -i "$forbidden" $runtime_paths; then
  echo "ISO-MUST-001/002/006 failed: forbidden old-system reference found"
  exit 1
fi

if rg -n '/Users/.*/muchen-talent-supply-system|\.\./muchen-talent-supply-system' $runtime_paths; then
  echo "ISO-MUST-001 failed: old repository path reference found"
  exit 1
fi

first_revision=$(find migrations/versions -type f -name '*.py' -maxdepth 1 | sort | head -n 1)
if test "$(basename "$first_revision")" != "0001_initial.py"; then
  echo "ISO-MUST-003 failed: migration history must start at 0001_initial.py"
  exit 1
fi

echo "isolation checks passed"

