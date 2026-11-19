#!/bin/sh
# Usage: ./reproduce.sh /path/to/Proteus-core /path/to/new/output
set -eu
here=$(CDPATH= cd "$(dirname "$0")" && pwd)
src=$1
out=$2
test ! -e "$out"
mkdir -p "$out"
out=$(CDPATH= cd "$out" && pwd)
pin=8ea2cdaf4195ae24e941354f68d4e97335d139d7
for mode in base after; do
    tree="$out/src-$mode"
    mkdir -p "$tree" "$out/$mode"
    git -C "$src" archive "$pin" | tar -x -C "$tree"
    if test "$mode" = after; then
        (cd "$tree" && git apply "$here/active-ids.patch")
    fi
    mkdir -p "$tree/crates/proteus-session-semantics/examples"
    cp "$here/probe.rs" "$tree/crates/proteus-session-semantics/examples/active_ids_probe.rs"
    (cd "$tree" &&
        CARGO_TARGET_DIR="$out/target-$mode" cargo test --release --locked -p proteus-session-semantics &&
        CARGO_TARGET_DIR="$out/target-$mode" cargo rustc --release --locked -p proteus-session-semantics --example active_ids_probe &&
        cp "$out/target-$mode/release/examples/active_ids_probe" "$out/$mode/probe" &&
        CARGO_TARGET_DIR="$out/target-$mode" cargo rustc --release --locked -p proteus-session-semantics --example active_ids_probe -- --cfg count_allocs &&
        cp "$out/target-$mode/release/examples/active_ids_probe" "$out/$mode/probe-alloc")
done
cp "$here/pair.sh" "$out/"
sh "$out/pair.sh" | tee "$out/pair.log"
