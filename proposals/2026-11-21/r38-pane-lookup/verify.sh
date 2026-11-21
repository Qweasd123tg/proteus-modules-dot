#!/usr/bin/env bash
# Usage: bash verify.sh /path/to/Proteus-desktop
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
repo=$(cd -- "${1:?provide Proteus-desktop checkout}" && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
git clone --quiet --local --no-checkout "$repo" "$work/repo"
cd "$work/repo"
git checkout --quiet --detach "$base"
export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-"$work/target"}
mkdir -p crates/tabs/examples
cp "$here/probe.rs" crates/tabs/examples/r38_pane_lookup.rs
for arm in stock candidate; do
    if [[ $arm == candidate ]]; then
        git apply --check "$here/source.patch"
        git apply "$here/source.patch"
        git diff --check
    fi
    cargo test --locked -p proteus-tabs --lib
    cargo run --quiet --locked --release -p proteus-tabs --example r38_pane_lookup -- "$arm"
done
