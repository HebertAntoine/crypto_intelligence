#!/usr/bin/env bash
#
# One full refresh: collect, re-analyse, then rebuild the snapshots the app
# reads. Run twice a day by the systemd timer in deploy/.
#
# The order matters. The Flutter app does not call the backend; it reads the
# JSON in app/assets/api_snapshots. Collecting without exporting leaves the
# screen showing the previous day's reading while the database is current, which
# is how a page ends up labelled "live" over data that is not.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/data/refresh_logs"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/refresh_$STAMP.log"

log() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$LOG"; }

cd "$ROOT" || exit 1
# The package lives under backend/, which is why the export script adds it to
# sys.path itself. The CLI needs the same, or it cannot import crypto_intel.
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
log "refresh start"

status=0

# Each step is allowed to fail on its own. A provider outage must not stop the
# remaining steps: a partial refresh with a stale family declared is better than
# no refresh at all, and the freshness layer already reports what is missing.
run_step() {
  local name="$1"; shift
  log "→ $name"
  if timeout "${STEP_TIMEOUT:-1800}" "$@" >>"$LOG" 2>&1; then
    log "✓ $name"
  else
    local code=$?
    log "✗ $name (code $code)"
    status=1
  fi
}

run_step "collect"  "$PY" -m crypto_intel.cli collect
run_step "analyze"  "$PY" -m crypto_intel.cli analyze
run_step "snapshots" "$PY" scripts/export_flutter_static_api.py --in-process

# The snapshot timestamps are what the screen shows. Report them so a failed
# export is visible in the log rather than only in the app.
log "snapshot freshness:"
"$PY" - <<'PYEOF' >>"$LOG" 2>&1
import json, pathlib, datetime
root = pathlib.Path(__file__).resolve().parents[0]
snap = pathlib.Path("app/assets/api_snapshots")
now = datetime.datetime.now(datetime.UTC)
for path in sorted(snap.glob("future__*__horizon-7d.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    as_of = data.get("as_of")
    age = "?"
    if as_of:
        parsed = datetime.datetime.fromisoformat(as_of)
        age = f"{(now - parsed).total_seconds() / 3600:.1f} h"
    print(f"  {path.name:<44} as_of={str(as_of)[:19]}  age={age}")
PYEOF

log "refresh done (status $status)"
exit "$status"
