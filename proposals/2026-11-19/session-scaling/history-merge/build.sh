#!/bin/bash
set -eu
p=$(cd "$(dirname "$0")" && pwd)
deps=${DEPS:?set DEPS to Cargo release deps with matching UUID/serde_json/proteus_contracts}
RUSTC=${RUSTC:-rustc}
for v in base after; do
 cp "$p/harness.rs" "$p/$v/src/main.rs"
 for mode in test bench alloc; do
  flags=()
  case $mode in test) flags=(--test);; alloc) flags=(--cfg alloc_counts);; esac
  "$RUSTC" --edition=2024 -C debuginfo=0 -C opt-level=3 -L dependency="$deps" \
   --extern proteus_contracts="$(echo "$deps"/libproteus_contracts-*.rlib)" \
   --extern uuid="$(echo "$deps"/libuuid-*.rlib)" \
   --extern serde_json="$(echo "$deps"/libserde_json-*.rlib)" \
   "${flags[@]}" "$p/$v/src/main.rs" -o "$p/$v/$mode"
 done
done
