#!/usr/bin/env bash
# Pass a local Proteus-desktop checkout containing the exact base commit.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
source_repo=$(cd -- "${1:?usage: bash verify.sh /path/to/Proteus-desktop}" && pwd)
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
git clone --quiet --local --no-checkout "$source_repo" "$work/repo"
cd "$work/repo"
git checkout --quiet --detach "$base"
export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-"$work/target"}
export PROTEUS_TERMINAL_ENGINE=alacritty SHELL=/bin/sh
cargo test --locked -p proteus-terminal --lib -- --test-threads=1
git apply --check "$here/source.patch"
git apply "$here/source.patch"
git diff --check
cargo test --locked -p proteus-terminal --lib -- --test-threads=1
probe=crates/terminal/examples/r36_alacritty_snapshot
mkdir -p "$probe"
cp "$here/probe.rs" "$probe/main.rs"
git show "$base:crates/terminal/src/alacritty_screen.rs" > "$probe/stock.rs"
cp crates/terminal/src/alacritty_screen.rs "$probe/candidate.rs"
cp crates/terminal/src/screen.rs "$probe/screen.rs"
cargo run --locked --release -p proteus-terminal --example r36_alacritty_snapshot
