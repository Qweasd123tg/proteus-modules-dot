#!/usr/bin/env bash
# Two clean copies. Requires Rust 1.95.0, Linux build tools, and local Git checkouts.
# bash reproduce.sh /path/to/Proteus-core /path/to/Proteus-modules NEW_OUTPUT_DIR
set -euo pipefail
core=${1:?expected Core checkout}; modules=${2:?expected Modules checkout}; out=${3:?expected new output directory}
bundle=$(cd "$(dirname "$0")" && pwd)
cpin=8ea2cdaf4195ae24e941354f68d4e97335d139d7
mpin=37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979
git -C "$core" cat-file -e "$cpin^{commit}"; git -C "$modules" cat-file -e "$mpin^{commit}"
mkdir "$out"; out=$(cd "$out" && pwd)
git clone --quiet --no-checkout -- "$modules" "$out/modules"
git -C "$out/modules" checkout --quiet --detach "$mpin"
git clone --quiet --no-checkout -- "$core" "$out/core"
git -C "$out/core" checkout --quiet --detach "$cpin"
export CARGO_INCREMENTAL=0 RUSTFLAGS='-C debuginfo=0' CARGO_BUILD_JOBS=3 CARGO_PROFILE_DEV_DEBUG=0
(cd "$out/modules"; CARGO_TARGET_DIR="$out/module-target" cargo build --locked -p proteus-reference-module -p proteus-session-storage-module)
export PROTEUS_TEST_REFERENCE_MODULE="$out/module-target/debug/proteus-reference-module"
export PROTEUS_TEST_SESSION_STORAGE_MODULE="$out/module-target/debug/proteus-session-storage-module"
export CARGO_TARGET_DIR="$out/core-target"
cd "$out/core"
p=crates/proteus-core/src/app_server/http/sse.rs
git apply --check --whitespace=error "$bundle/probe.patch"; git apply --whitespace=error "$bundle/probe.patch"
for v in baseline candidate; do
    if test "$v" = candidate; then
        git apply --check --whitespace=error "$bundle/sse-direct-frame.patch"
        git apply --whitespace=error "$bundle/sse-direct-frame.patch"
    fi
    cargo test --release --locked -p proteus-core --lib 'app_server::http::tests::sse::' -- --test-threads=1 2>&1 | tee "$out/$v-tests.log"
    grep -q '3 passed; 0 failed' "$out/$v-tests.log"
    deps="$CARGO_TARGET_DIR/release/deps"
    bin=$(find "$deps" -maxdepth 1 -type f -executable -name 'proteus_core-*' -print -quit)
    cp "$bin" "$out/$v-bin"
    sed -n '/^pub(super) fn encode_sse_output/,$p' "$p" > "$out/$v-frame.rs"
    libs=()
    for name in proteus_contracts serde_json bytes uuid; do
        lib=$(find "$deps" -maxdepth 1 -name "lib$name-*.rlib" -print -quit)
        libs+=(--extern "$name=$lib")
    done
    FRAME_FN_FILE="$out/$v-frame.rs" rustc --edition 2024 -O -L dependency="$deps" "${libs[@]}" "$bundle/allocation.rs" -o "$out/$v-heap"
    "$out/$v-heap" | tee "$out/$v-heap.log"
    "$out/$v-heap" sweep > "$out/$v-sweep.csv"
done
for phase in 1 2; do
    if test "$phase" = 1; then versions='baseline candidate'; else versions='candidate baseline'; fi
    for v in $versions; do
        "$out/$v-bin" measure_initial_frame --ignored --nocapture --test-threads=1 | tee "$out/$v-$phase.log"
        grep -q '1 passed; 0 failed' "$out/$v-$phase.log"
    done
done
