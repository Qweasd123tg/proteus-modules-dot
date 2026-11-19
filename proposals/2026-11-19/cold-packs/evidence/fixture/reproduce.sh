#!/bin/bash
# This script builds an instrumented COPY. Source trees are never modified.
set -euo pipefail
: "${1:?supply Core clone containing 2aad0ba}"
: "${2:?supply Modules clone containing 2c2cee4}"
: "${3:?new working directory (must not yet exist)}"
here=$(cd "$(dirname "$0")" && pwd); core=$(realpath "$1"); modules=$(realpath "$2")
mkdir "$3"; here_work=$(cd "$3" && pwd)
mkdir "$here_work"/{core,modules}
git -C "$core" archive 2aad0ba29311f0dbf7c107efc281abc1202ce4c4 | tar -x -C "$here_work/core"
git -C "$modules" archive 2c2cee47ea76df12c6e208839594e32470a2c3f1 | tar -x -C "$here_work/modules"
python3 "$here/instrument.py" "$here_work/core"
# The production functions remain in place; omit other libtest registrations to lower peak compiler memory.
python3 "$here/strip-tests.py" "$here_work/core"
export CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 RUSTFLAGS='-C debuginfo=0'
(cd "$here_work/modules"; cargo build --locked --release -p proteus-session-storage-module; CARGO_PROFILE_DEV_DEBUG=0 cargo build --locked -p proteus-reference-module)
export PROTEUS_TEST_REFERENCE_MODULE="$here_work/modules/target/debug/proteus-reference-module"
export PROTEUS_TEST_SESSION_STORAGE_MODULE="$here_work/modules/target/release/proteus-session-storage-module"
cd "$here_work/core"
R9_CASES=${R9_CASES:-100,5000,50000} cargo --config 'profile.release.package.proteus-contracts.opt-level=1' --config 'profile.release.package.proteus-core.opt-level=1' --config 'profile.release.package.proteus-core.codegen-units=64' test --release --locked -p proteus-core --lib app_server::http::tests::session_reads::r9_real_turn_fixed_active_history -- --exact --nocapture --test-threads=1
