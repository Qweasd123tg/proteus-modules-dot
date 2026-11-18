#!/bin/sh
# Linux, Rust 1.95, exact checkout accessible locally, Cargo deps available.
set -eu
pkg=$(cd "$(dirname "$0")" && pwd)
src=$(cd "$1" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-"$work/target"}
for side in before after; do
    git clone -q --shared --no-checkout "$src" "$work/$side"
    git -C "$work/$side" checkout -q --detach 37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979
    if test "$side" = after; then git -C "$work/$side" apply --whitespace=error "$pkg/sized-pending-record.patch"; fi
    touch "$work/$side/storage/session-storage/src/snapshot.rs" "$work/$side/components/session-storage-module/src/main.rs"
    (cd "$work/$side" && cargo build --release --locked -p proteus-session-storage-module)
    cp "$CARGO_TARGET_DIR/release/proteus-session-storage-module" "$work/worker-$side"
done
if cmp -s "$work/worker-before" "$work/worker-after"; then echo "identical workers; stop" >&2; exit 1; fi
python3 "$pkg/wire_probe.py" "$work/worker-before" "$work/worker-after"
