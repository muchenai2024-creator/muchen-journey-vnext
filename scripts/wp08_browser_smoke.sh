#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
spec_path="$repo_root/config/wp08_browser_smoke.json"
evidence_dir="$repo_root/output/playwright/wp08"
session_name="wp08-smoke"
local_services_started=0

cleanup() {
    bash "$PLAYWRIGHT_CLI" -s="$session_name" close >/dev/null 2>&1 || true
    if [ "$local_services_started" -eq 1 ]; then
        docker compose --project-directory "$repo_root" stop web api db >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

python3 "$repo_root/scripts/wp08_readiness.py" browser-preflight --spec "$spec_path"
mkdir -p "$evidence_dir"
runtime_config="$evidence_dir/cli.config.json"

if [ "${BROWSER_SCOPE:-local}" = "local" ]; then
    browser_port=$(python3 -c 'import os, urllib.parse; print(urllib.parse.urlparse(os.environ["BROWSER_BASE_URL"]).port or 80)')
    MJ_DB_PORT=${MJ_DB_PORT:-35432}
    MJ_API_PORT=${MJ_API_PORT:-38000}
    MJ_WEB_PORT=${MJ_WEB_PORT:-$browser_port}
    export MJ_DB_PORT MJ_API_PORT MJ_WEB_PORT
    local_services_started=1
    docker compose --project-directory "$repo_root" up --build -d --wait db api web
fi

python3 - "$runtime_config" "$PLAYWRIGHT_CHROMIUM_EXECUTABLE" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "browser": {
                "launchOptions": {
                    "executablePath": sys.argv[2],
                    "headless": True,
                },
                "contextOptions": {"viewport": {"width": 1440, "height": 900}},
            }
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

cd "$evidence_dir"
pwcli() {
    bash "$PLAYWRIGHT_CLI" -s="$session_name" "$@"
}

pwcli open "${BROWSER_BASE_URL%/}/ops" --config "$runtime_config"
pwcli snapshot >snapshot-initial.txt

python3 - "$spec_path" <<'PY' | while IFS=' ' read -r name width height; do
import json
import sys

spec = json.load(open(sys.argv[1], encoding="utf-8"))
for viewport in spec["viewports"]:
    print(viewport["name"], viewport["width"], viewport["height"])
PY
    pwcli resize "$width" "$height"
    pwcli reload
    pwcli snapshot >"snapshot-$name.txt"
    pwcli --raw eval "() => JSON.stringify({viewportWidth: window.innerWidth, documentWidth: document.documentElement.scrollWidth, focusableCount: document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]:not([tabindex=\"-1\"])').length})" >"metrics-$name.json"
    python3 - "$name" "$width" "metrics-$name.json" <<'PY'
import json
import sys
from pathlib import Path

name, expected_width, path = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
raw = path.read_text(encoding="utf-8").strip()
try:
    metrics = json.loads(json.loads(raw) if raw.startswith('"') else raw)
except json.JSONDecodeError as error:
    raise SystemExit(f"invalid browser metrics for {name}: {raw!r}: {error}")
if metrics["viewportWidth"] != expected_width:
    raise SystemExit(f"viewport mismatch for {name}: {metrics}")
if metrics["documentWidth"] > metrics["viewportWidth"]:
    raise SystemExit(f"horizontal overflow for {name}: {metrics}")
if metrics["focusableCount"] < 1:
    raise SystemExit(f"no keyboard-focusable control for {name}: {metrics}")
PY
    pwcli press Tab
    pwcli --raw eval "() => document.activeElement !== document.body" >"focus-$name.txt"
    grep -Eq '(^|[^a-z])true([^a-z]|$)' "focus-$name.txt"
    pwcli screenshot --filename "wp08-$name.png" --full-page
done

pwcli console error >console-errors.txt
if grep -Eiq '(\[error\]|console\.error|uncaught|pageerror)' console-errors.txt; then
    printf '%s\n' "browser console contains errors" >&2
    exit 2
fi

printf '%s\n' "WP08_BROWSER_SMOKE=PASS"
