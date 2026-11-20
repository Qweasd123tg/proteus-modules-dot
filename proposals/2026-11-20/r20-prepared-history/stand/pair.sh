#!/bin/bash
# No compiles in timed windows. Immutable named output dirs; failed first attempts retained.
set -uo pipefail
cd "$(dirname "$0")/.."
sourceid=2547f15f2a7b511c20b9b34ecf2d4872557608b7
: "${CANDIDATE_SHA:?Must be supplied from final producer receipt}"
bridge="$PWD/r20-desktop/desktop_api.py"
run(){
  state=$1;shift; kind=$1;shift; label=$1;shift
  printf '%s start %s %s %s\n' "$(date -u --iso-8601=ns)" "$kind" "$state" "$label"
  if [ "$kind" = stock ]; then
    r20-bench/run.sh "$state" "$label" --desktop-bridge "$bridge" "$@"
  else
    CORE_BIN="$PWD/r20-evidence/proteus-candidate-final" CORE_SHA="$CANDIDATE_SHA" CORE_COMMIT="$sourceid" r20-bench/run.sh "$state" "$label" --desktop-bridge "$bridge" "$@"
  fi
  rc=$?
  printf '%s end %s rc=%s\n' "$(date -u --iso-8601=ns)" "$label" "$rc"
  # Keep failing result intact; execute both arms even if one timed out.
}
run indexed stock indexed-A1
run indexed candidate indexed-B1
run absent candidate absent-B
run absent stock absent-A
run indexed candidate indexed-B2
run indexed stock indexed-A2
run indexed stock wire-A --wire
run indexed candidate wire-B --wire
