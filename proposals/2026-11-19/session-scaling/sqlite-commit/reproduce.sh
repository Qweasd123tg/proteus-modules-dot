#!/bin/sh
# Linux, Python 3, Rust/Cargo with dependencies for the pinned upstream checkout.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$1" && pwd)
out=$2; mkdir -p "$out"; out=$(cd "$out" && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/proteus-storage-r6.XXXXXX")
trap 'rm -rf "$work"' EXIT
export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-"$work/target"}
for side in before after; do
    git clone -q --shared --no-checkout "$repo" "$work/$side"
    git -C "$work/$side" checkout -q --detach 37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979
    if [ "$side" = after ]; then git -C "$work/$side" apply --check "$here/commit.patch"; git -C "$work/$side" apply "$here/commit.patch"; fi
    cd "$work/$side"
    touch storage/session-storage/src/codec.rs storage/session-storage/src/service/commits.rs
    touch storage/session-storage/src/snapshot.rs components/session-storage-module/src/main.rs
    if [ "$side" = before ]; then sed 's/PROBE_BORROWentry/\&entry/' "$here/bound_probe.rs"; else sed 's/PROBE_BORROWentry/entry/' "$here/bound_probe.rs"; fi >> storage/session-storage/src/tests/performance.rs
    cargo build --release --locked -p proteus-session-storage-module
    cp "$CARGO_TARGET_DIR/release/proteus-session-storage-module" "$work/$side-worker"
    cargo test --release --locked -p session-storage --lib >"$out/$side-tests.log"
    cargo test --release --locked -p session-storage --lib -- --ignored --exact tests::performance::perf6_canonical_commit_byte_limit >"$out/$side-boundary.log"
    cargo test --release --locked -p proteus-session-storage-module --test process >"$out/$side-process.log"
done
if cmp -s "$work/before-worker" "$work/after-worker"; then echo 'identical binaries; stopping' >&2; exit 1; fi
cd "$work"
python3 "$here/wire_probe.py" "$work/before-worker" "$work/after-worker" --pairs 6 --tmpdir "$work" --out "$out/wire.json"
python3 "$here/wire_probe.py" "$work/before-worker" "$work/after-worker" --pairs 10 --large-chars 4194304 --tmpdir "$work" --out "$out/wire_repeat.json"
