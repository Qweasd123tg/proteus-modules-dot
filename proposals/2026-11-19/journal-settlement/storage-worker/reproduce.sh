#!/usr/bin/env bash
# Usage: bash reproduce.sh /path/to/Proteus-modules /new/output [--cpu N]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$1" && pwd)
out=$(mkdir -p "$2" && cd "$2" && pwd); shift 2
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
pin=37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979
export CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS:-2}
for arm in base after; do
  git clone -q --local --no-checkout "$repo" "$work/$arm"
  (
    cd "$work/$arm"; git checkout -q --detach "$pin"
    if [[ $arm == after ]]; then git apply --check "$here/compare.patch"; git apply "$here/compare.patch"; fi
    cat "$here/probe.rs" >>storage/session-storage/src/tests/performance.rs
    export CARGO_TARGET_DIR="$work/$arm-target"
    cargo test --locked --release -p session-storage --lib --no-run --message-format=json >"$out/$arm-build.jsonl"
    binary=$(python3 -c 'import json,sys; print(next(i["executable"] for l in open(sys.argv[1]) if (i:=json.loads(l)).get("executable") and i["target"]["name"]=="session_storage"))' "$out/$arm-build.jsonl")
    cp "$binary" "$work/$arm-unit-tests"
    "$binary" --test-threads=1 >"$out/$arm-tests.log"
    cargo test --release --locked -p proteus-session-storage-module --test process >"$out/$arm-process.log"
  )
done
python3 "$here/measure.py" "$work/base-unit-tests" "$work/after-unit-tests" "$out/results" "$@"
