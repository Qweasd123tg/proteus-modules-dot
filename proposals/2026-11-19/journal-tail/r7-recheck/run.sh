#!/bin/bash
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
out="$repo/perf-r8-baseline"
cd "$repo/perf-r7-parent/candidate" || exit 2
export PROTEUS_TEST_REFERENCE_MODULE="$repo/perf-round3-core/module-target/debug/proteus-reference-module"
export PERF7_CASES=50000
bench="$repo/perf-r7-parent/bench-candidate"
stock=/tmp/perf6-modules/base/worker
cand="$repo/perf-r7-storage/after/worker"
cpu=2
date -u '+%FT%TZ' > "$out/start-time.txt"
sha256sum "$bench" "$stock" "$cand" "$PROTEUS_TEST_REFERENCE_MODULE" > "$out/input-sha256.txt" || exit 2
for name in A1 B1 B2 A2; do
  case "$name" in
    A*) export PROTEUS_TEST_SESSION_STORAGE_MODULE="$stock";;
    B*) export PROTEUS_TEST_SESSION_STORAGE_MODULE="$cand";;
  esac
  date -u '+%FT%TZ' > "$out/$name.start"
  taskset -c "$cpu" "$bench" --exact app_server::http::tests::session_reads::perf7_real_turn_fixed_active_history --nocapture --test-threads=1 > "$out/$name.log" 2>&1
  rc=$?
  echo "$rc" > "$out/$name.exit"
  date -u '+%FT%TZ' > "$out/$name.end"
  if [[ $rc != 0 ]]; then echo "failed: $name $rc"; fi
done
