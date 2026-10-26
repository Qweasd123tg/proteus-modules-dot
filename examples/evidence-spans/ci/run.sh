#!/usr/bin/env bash
# Only our module/helper, own executable wire fixtures and authored demonstration.
set -euo pipefail
workspace=examples/evidence-spans
artifacts=validation/evidence-spans
test -d "$artifacts"
test ! -e "$artifacts/workspace-tests.log"
cargo +1.95.0 fmt --all --check --manifest-path "$workspace/Cargo.toml" 2>&1 | tee "$artifacts/format.log"
cargo +1.95.0 test --locked --workspace --manifest-path "$workspace/Cargo.toml" -- --test-threads=1 2>&1 | tee "$artifacts/workspace-tests.log"
cargo +1.95.0 run --locked --manifest-path "$workspace/Cargo.toml" --example authored_quote_audit > "$artifacts/positive.json" 2> "$artifacts/positive-build.log"
cargo +1.95.0 run --locked --manifest-path "$workspace/Cargo.toml" --example authored_quote_audit -- --wrong-quote > "$artifacts/negative.json" 2> "$artifacts/negative-build.log"
sha256sum "$CARGO_TARGET_DIR/debug/proteus-example-evidence-spans" "$CARGO_TARGET_DIR/debug/examples/authored_quote_audit" > "$artifacts/binaries.sha256"
python3 -B -I "$workspace/ci/verify_artifacts.py" --workspace "$workspace" --artifacts "$artifacts"
