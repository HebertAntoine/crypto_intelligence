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

# One pipeline writer at a time. A manual run launched while the 07:00 timer is
# still working would otherwise interleave two collections into the same
# database and export a set built from both.
LOCK="$ROOT/data/.refresh.lock"
mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"
# The full pass waits for the lock instead of giving up. The light pass fires
# every 15 minutes, including at 07:00 and 19:00: a non-blocking lock made the
# twice-daily run skip itself whenever the two coincided, with nothing to retry
# it before the next half-day. A light pass takes minutes; 15 is ample.
if ! flock -w "${REFRESH_LOCK_WAIT:-900}" 9; then
  echo "$(date -u +%H:%M:%S) refresh lock still held after waiting, skipping this start" >&2
  exit 75   # EX_TEMPFAIL: not a failure, simply not this run's turn
fi
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
# The regime moves slowly and its written history moves once a month.
run_step "cycle-snapshot" "$PY" -m crypto_intel.cli cycle-snapshot
# One identifier for the whole cycle, stamped on every snapshot, so a mixed set
# is detectable rather than invisible.
RUN_ID="run_$(date -u +%Y%m%dT%H%M%SZ)"
log "run_id $RUN_ID"
run_step "snapshots" "$PY" scripts/export_flutter_static_api.py --in-process --run-id "$RUN_ID"

# The run reports its own state rather than waiting to be asked. health.json is
# written on every cycle so a person, a page or a later check reads the same
# thing the pipeline concluded.
log "health:"
"$PY" -m crypto_intel.cli health --json >>"$LOG" 2>&1 || status=1

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

# Exit codes carry meaning: a failed optional source is a degraded success, an
# unusable export is a failure. The timer's journal then says which happened.
if [ "$status" -eq 0 ]; then
  log "refresh done: SUCCESS"
  exit 0
fi
if grep -q "✗ snapshots" "$LOG"; then
  log "refresh done: FAILED (export unusable, previous set kept)"
  exit 1
fi
log "refresh done: DEGRADED_SUCCESS (a step failed, snapshots published)"
exit 0
