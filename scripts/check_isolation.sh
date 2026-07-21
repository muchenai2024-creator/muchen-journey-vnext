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

if command -v rg >/dev/null 2>&1; then
  scanner=rg
elif command -v grep >/dev/null 2>&1; then
  scanner=grep
else
  echo "ISO-MUST-001 failed: neither rg nor grep is available" >&2
  exit 2
fi

scan_runtime_paths() {
  pattern=$1
  if test "$scanner" = rg; then
    if rg -n -i -- "$pattern" $runtime_paths; then
      status=0
    else
      status=$?
    fi
  else
    if grep -R -n -i -E \
      --exclude-dir=.git --exclude-dir=.next --exclude-dir=node_modules \
      --exclude-dir=__pycache__ -- "$pattern" $runtime_paths; then
      status=0
    else
      status=$?
    fi
  fi
  case "$status" in
    0) return 0 ;;
    1) return 1 ;;
    *)
      echo "ISO-MUST-001 failed: $scanner scanner execution failed with status $status" >&2
      exit "$status"
      ;;
  esac
}

if scan_runtime_paths "$forbidden"; then
  echo "ISO-MUST-001/002/006 failed: forbidden old-system reference found"
  exit 1
fi

if scan_runtime_paths '/Users/.*/muchen-talent-supply-system|\.\./muchen-talent-supply-system'; then
  echo "ISO-MUST-001 failed: old repository path reference found"
  exit 1
fi

first_revision=$(find migrations/versions -maxdepth 1 -type f -name '*.py' | sort | head -n 1)
if test "$(basename "$first_revision")" != "0001_initial.py"; then
  echo "ISO-MUST-003 failed: migration history must start at 0001_initial.py"
  exit 1
fi

echo "isolation checks passed"
