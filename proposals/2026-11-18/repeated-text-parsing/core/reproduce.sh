#!/usr/bin/env bash
# fresh copies of local checkouts; requires Bash, Git, Rust 1.95.0, Node and native build dependencies
set -euo pipefail
bundle=$(cd "$(dirname "$0")" && pwd); core=${1:?Core checkout}; mods=${2:?Modules checkout}; out=${3:?new output directory}
mkdir "$out"; out=$(cd "$out" && pwd)
git clone --quiet --no-checkout -- "$core" "$out/core"
git clone --quiet --no-checkout -- "$mods" "$out/modules"
git -C "$out/core" checkout --quiet --detach 8ea2cdaf4195ae24e941354f68d4e97335d139d7
git -C "$out/modules" checkout --quiet --detach 37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979
git -C "$out/core" apply --check --whitespace=error "$bundle/instrumentation.patch"
git -C "$out/core" apply --whitespace=error "$bundle/instrumentation.patch"
node "$bundle/provider.mjs" "$out/modules" "$out/core/crates/proteus-core/r4-provider.json"
(cd "$out/modules"; CARGO_TARGET_DIR="$out/modules-target" cargo build --locked -p proteus-session-storage-module)
export PROTEUS_TEST_SESSION_STORAGE_MODULE="$out/modules-target/debug/proteus-session-storage-module"
cd "$out/core"; export CARGO_TARGET_DIR="$out/core-target" CARGO_INCREMENTAL=0 RUSTFLAGS='-C debuginfo=0'
cargo --config 'profile.release.package.proteus-core.opt-level=0' test --locked --release -p proteus-core --lib round4_projection_trace -- --nocapture --test-threads=1 2>&1 | tee "$out/trace.log"
grep -q '1 passed; 0 failed' "$out/trace.log"
