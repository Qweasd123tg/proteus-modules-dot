#!/usr/bin/env bash
set -eu
source /workspace/shared/proteus-toolchain/env.sh
cd /workspace/shared/proteus-replay-integrity-89997df9
export CARGO_TARGET_DIR=/workspace/shared/proteus-runtime-audit-target
export CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0
export PROTEUS_REPLAY_AUDIT_EVIDENCE=/workspace/shared/replay-integrity-evidence/canonical-sessions
cargo test --offline --locked -p proteus-core --lib core::workflow_replay -- --nocapture
# These two desired invariants deliberately fail on the audited production baseline:
# cargo test --offline --locked -p proteus-core --lib audit_capabilities -- --ignored --nocapture
