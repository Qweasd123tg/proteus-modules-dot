#!/usr/bin/env bash
# A temporary Cargo project tests the actual source modules without GPUI.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "${1:?usage: bash verify.sh /path/to/Proteus-desktop}" && pwd)
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
git clone --quiet --local --no-checkout "$repo" "$work/desktop"
git -C "$work/desktop" checkout --quiet --detach "$base"
mkdir -p "$work/headless/src"
cd "$work/headless"
cp "$here/probe.rs" src/main.rs
cp "$here/test.rs" src/lib.rs
cp ../desktop/src/sessions.rs src/stock.rs
git -C ../desktop apply --check "$here/source.patch"
git -C ../desktop apply "$here/source.patch"
git -C ../desktop diff --check
cp ../desktop/src/sessions.rs src/candidate.rs
cp ../desktop/src/conversations.rs src/conversations.rs
cp ../desktop/src/agents/codex/types.rs src/codex_types.rs
cp ../desktop/Cargo.lock .
cp ../desktop/rust-toolchain.toml .
cat > Cargo.toml <<'TOML'
[package]
name = "proteus-session-sort-proof"
version = "0.0.0"
edition = "2024"
publish = false
[dependencies]
proteus-tabs = { path = "../desktop/crates/tabs" }
proteus-contracts = { git = "https://github.com/Proteus-harness/Proteus-core.git", rev = "7cbc7206f03fac130d05bed2844de275476fedc8" }
serde = { version = "=1.0.229", features = ["derive"] }
serde_json = "=1.0.152"
uuid = { version = "=1.28.0", features = ["v4"] }
[lints.rust]
unexpected_cfgs = { level = "warn", check-cfg = ['cfg(base)'] }
TOML
# Drop unrelated native dependency entries from the copied lock on initial resolution.
cargo test --lib -- --test-threads=1
RUSTFLAGS="${RUSTFLAGS:-} --cfg base" cargo test --locked --lib -- --test-threads=1
cargo run --locked --release
