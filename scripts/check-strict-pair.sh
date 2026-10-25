#!/usr/bin/env bash
# Ephemeral authored-only CI gate; no live providers or project hooks.
set -euo pipefail
: "${STRICT_PAIR_DIR:?Set the repository-relative strict workspace directory}"
: "${PAIRING_REVIEW_MANIFEST:?Set the repository-relative independent review Cargo.toml}"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$PWD/target}"
export CARGO_BUILD_JOBS=2
export CARGO_TERM_COLOR=never
# Use a separate CI job so v1 binary paths/evidence cannot be replaced in a
# concurrently running historical gate. Install toolchain in the workflow first.
mkdir -p validation
mkdir validation/strict-pair
cargo +1.95.0 fmt --all --check --manifest-path "$STRICT_PAIR_DIR/Cargo.toml"
cargo +1.95.0 test --locked --workspace --manifest-path "$STRICT_PAIR_DIR/Cargo.toml" 2>&1 | tee validation/strict-pair/workspace-tests.log
cargo +1.95.0 fmt --check --manifest-path "$PAIRING_REVIEW_MANIFEST"
cargo +1.95.0 test --locked --manifest-path "$PAIRING_REVIEW_MANIFEST" 2>&1 | tee validation/strict-pair/independent-tests.log
cargo +1.95.0 run --locked --manifest-path "$STRICT_PAIR_DIR/Cargo.toml" \
  -p proteus-example-json-contracts --example strict_authored_fixture \
  > validation/strict-pair/positive.json
cargo +1.95.0 run --locked --manifest-path "$STRICT_PAIR_DIR/Cargo.toml" \
  -p proteus-example-json-contracts --example strict_authored_fixture -- --fail \
  > validation/strict-pair/negative.json
cargo +1.95.0 run --locked --manifest-path "$STRICT_PAIR_DIR/Cargo.toml" \
  -p proteus-example-json-contracts --example strict_json_policy \
  < "$STRICT_PAIR_DIR/json-contracts/fixtures/suite.json" \
  > validation/strict-pair/receipt-policy.json
python3 -I scripts/verify_strict_artifacts.py --workspace "$STRICT_PAIR_DIR" \
  --artifacts validation/strict-pair \
  --workspace-log validation/strict-pair/workspace-tests.log \
  --review-log validation/strict-pair/independent-tests.log
