#!/usr/bin/env bash
# Use a local checkout containing the pinned Desktop commit, with its Rust toolchain.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "${1:?usage: bash verify.sh /path/to/Proteus-desktop [#245.patch]}" && pwd)
stack=${2:+$(realpath "$2")}
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
git -C "$repo" archive "$base" | tar -x -C "$work"
cd "$work"
export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-"$work/target"}
CARGO_TARGET_DIR=$(realpath -m "$CARGO_TARGET_DIR")
cargo test --locked -p proteus-diff --lib
cp -r crates/diff/src baseline
git apply --check "$here/source.patch"
git apply "$here/source.patch"
cargo test --locked -p proteus-diff --lib
rustfmt --edition=2024 --check crates/diff/src/lib.rs
cp -r crates/diff/src candidate

# Compile the two exact production crate roots against Cargo's locked serde.
deps="$CARGO_TARGET_DIR/debug/deps"
serde=$(find "$deps" -maxdepth 1 -name 'libserde-*.rlib' -print -quit)
for side in baseline candidate; do
  rustc --edition=2024 -O --crate-type rlib --crate-name "$side" "$side/lib.rs" \
    -L "dependency=$deps" --extern "serde=$serde" -o "lib$side.rlib"
done
for mode in timing alloc; do
  flags=()
  if [[ "$mode" == alloc ]]; then flags+=(--cfg count_alloc); fi
  rustc --edition=2024 -O "${flags[@]}" "$here/probe.rs" -L "dependency=$deps" \
    --extern baseline=libbaseline.rlib --extern candidate=libcandidate.rlib -o "$mode"
  "./$mode"
done
if [[ -n "$stack" ]]; then
  git apply --reverse "$here/source.patch"
  git apply --check "$stack"
  git apply "$stack"
  git apply --check "$here/source.patch"
  git apply "$here/source.patch"
  cargo test --locked -p proteus-diff --lib
fi
