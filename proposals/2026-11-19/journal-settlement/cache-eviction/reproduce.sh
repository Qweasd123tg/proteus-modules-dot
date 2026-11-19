#!/bin/sh
# Linux, Rust/Cargo and Python 3; dependencies from pinned Modules.
set -eu
here=$(CDPATH= cd "$(dirname "$0")" && pwd)
repo=$(CDPATH= cd "$1" && pwd); work=$2
test ! -e "$work"; mkdir -p "$work"; work=$(CDPATH= cd "$work" && pwd)
for side in base opt; do
    mkdir "$work/$side"
    git -C "$repo" archive 37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979 | tar -x -C "$work/$side"
    cd "$work/$side"
    if [ "$side" = opt ]; then git apply --check "$here/evict.patch"; git apply "$here/evict.patch"; fi
    export CARGO_TARGET_DIR="$work/target-$side"
    cargo build --release --locked -p proteus-session-storage-module
    cp "$CARGO_TARGET_DIR/release/proteus-session-storage-module" "$work/worker-$side"
    cat "$here/quota_control.rs" "$here/allocation_probe.rs" >> storage/session-storage/src/service/cache.rs
    cargo test --release --locked -p session-storage --lib -- --test-threads=1 > "$work/tests-$side.log"
    cargo test --release --locked -p session-storage --lib measure_cache_eviction_allocation -- --ignored --nocapture --test-threads=1 > "$work/alloc-$side.log"
done
python3 "$here/worker_probe.py" "$work/worker-base" --out "$work/baseline.json"
python3 "$here/compare.py" "$work/worker-base" "$work/worker-opt" --out "$work/comparison.json"
