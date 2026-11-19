#!/usr/bin/env bash
# Usage: run-payload-probe.sh /path/to/patched/modules /path/to/synthetic/journal.jsonl /new/build-dir
set -euo pipefail
src="$(realpath "$1")"; journal="$(realpath "$2")"; out="$(realpath -m "$3")"
mkdir "$out"; mkdir "$out/src"; cp "$src/storage/session-storage/src/codec/payload.rs" "$out/src/payload.rs"
sed 's@modules/storage/session-storage/src/codec/payload.rs@payload.rs@' "$(dirname "$0")/payload_probe.rs" > "$out/src/main.rs"
cat > "$out/Cargo.toml" <<'TOML'
[package]
name = "payload-probe"
version = "0.1.0"
edition = "2024"
[dependencies]
serde = {version = "1", features = ["derive"]}
serde_json = {version = "1", features = ["float_roundtrip"]}
TOML
cd "$out"
cargo build --release --offline
for arm in stock candidate candidate stock stock candidate candidate stock; do target/release/payload-probe "$journal" "$arm"; done
RUSTFLAGS="--cfg counting" cargo build --release --offline
for arm in stock candidate; do target/release/payload-probe "$journal" "$arm"; done
