#!/usr/bin/env bash
# Usage: bash reproduce.sh /path/to/Proteus-modules /new/output [cpu-for-workers]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); src=$(cd "$1" && pwd)
test ! -e "$2"; mkdir -p "$2"; out=$(cd "$2" && pwd); cpu=()
if [[ $# -ge 3 ]]; then cpu+=(--cpu "$3"); fi
pin=37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979
mkdir -p "$out/pairs" "$out/tmp"
export TMPDIR="$out/tmp" CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}"
for arm in baseline candidate; do
    git clone --local --no-checkout -q "$src" "$out/$arm"
    (
        cd "$out/$arm"; git checkout -q --detach "$pin"
        git apply --check "$here/compare-r7.patch"; git apply "$here/compare-r7.patch"
        if [[ $arm == candidate ]]; then git apply --check "$here/seek.patch"; git apply "$here/seek.patch"; fi
        export CARGO_TARGET_DIR="$out/$arm-target"
        cargo test --locked --release -p session-storage --lib -p proteus-session-storage-module --test process
        cargo build --locked --release -p proteus-session-storage-module
        cp "$CARGO_TARGET_DIR/release/proteus-session-storage-module" "$out/$arm-worker"
    ) >"$out/$arm-build.log" 2>&1
done
sha256sum "$out/"{baseline,candidate}-worker >"$out/binaries.sha256"
for i in {0..7}; do
    flip=(); if ((i%2)); then flip+=(--flip); fi
    python3 "$here/bench.py" "$out/baseline-worker" "$out/candidate-worker" "$out/pairs/pair-$i.csv" --pairs 3 "${cpu[@]}" "${flip[@]}"
done
python3 "$here/summarize.py" "$out/pairs" >"$out/summary.csv"
