#!/bin/sh
# Source: a checkout of Proteus-core with #220's active-ids, display and cursor
# candidate patches already applied, but not either patch in this directory.
# Usage: sh reproduce.sh <source-dir> <new-output-dir>
set -eu
h=$(CDPATH= cd "$(dirname "$0")" && pwd)
s=$(CDPATH= cd "$1" && pwd)
test ! -e "$2"
mkdir "$2"; out=$(CDPATH= cd "$2" && pwd)
for mode in base after; do
  dir="$out/src-$mode"
  mkdir -p "$dir" "$out/$mode"
  (cd "$s" && tar --exclude=.git --exclude=target -cf - .) | (cd "$dir" && tar -xf -)
  (cd "$dir"
   if [ "$mode" = after ]; then git apply "$h/batch-ids.patch"; git apply "$h/move-final.patch"; fi
   mkdir -p crates/proteus-session-semantics/examples
   cp "$h/probe.rs" crates/proteus-session-semantics/examples/fold_cost.rs
   export CARGO_TARGET_DIR="$out/target-$mode"
   cargo test --locked --release -p proteus-session-semantics
   if [ "$mode" = after ]; then set -- --cfg transfer; else set --; fi
   cargo rustc --locked --release -p proteus-session-semantics --example fold_cost -- "$@"
   cp "$CARGO_TARGET_DIR/release/examples/fold_cost" "$out/$mode/probe"
   cargo rustc --locked --release -p proteus-session-semantics --example fold_cost -- "$@" --cfg count_allocs
   cp "$CARGO_TARGET_DIR/release/examples/fold_cost" "$out/$mode/probe-alloc"
  )
done
python3 "$h/paired.py" "$out" > "$out/pairs.csv"
for n in 2000 10000 20000; do
  for mode in base after; do echo "$mode $n"; "$out/$mode/probe-alloc" "$n" 100 100 160; done
done > "$out/alloc.log"
