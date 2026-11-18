#!/usr/bin/env bash
# bash reproduce.sh /path/to/Proteus-core NEW_OUTPUT_DIRECTORY [PIN]
set -euo pipefail
repo=${1:?expected an existing Core checkout}
out=${2:?expected a new output directory}
pin=${3:-8ea2cdaf4195ae24e941354f68d4e97335d139d7}
bundle=$(cd "$(dirname "$0")" && pwd)
git -C "$repo" cat-file -e "$pin^{commit}"
mkdir "$out"
out=$(cd "$out" && pwd)
git clone --quiet --no-checkout -- "$repo" "$out/tree"
git -C "$out/tree" checkout --quiet --detach "$pin"
cd "$out/tree"
export CARGO_TARGET_DIR="$out/target" CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=4 RUSTFLAGS='-C debuginfo=0'
git apply --check --whitespace=error "$bundle/probe.patch"
git apply --whitespace=error "$bundle/probe.patch"
for v in baseline candidate; do
    if test "$v" = candidate; then
        git apply --check --whitespace=error "$bundle/repair-physical-pages.patch"
        git apply --whitespace=error "$bundle/repair-physical-pages.patch"
    fi
    cargo test --release --locked -p proteus-core --lib session_store::remote::view::tests -- --test-threads=1 2>&1 | tee "$out/$v-tests.log"
    grep -q '6 passed; 0 failed' "$out/$v-tests.log"
    bin=$(find "$CARGO_TARGET_DIR/release/deps" -maxdepth 1 -type f -executable -name 'proteus_core-*' -print -quit)
    cp "$bin" "$out/$v-bin"
done
for phase in 1 2; do
    if test "$phase" = 1; then variants='baseline candidate'; else variants='candidate baseline'; fi
    for v in $variants; do
        "$out/$v-bin" measure_cached_tool_repair --ignored --nocapture --test-threads=1 2>&1 | tee "$out/$v-$phase.log"
        grep -q '1 passed; 0 failed' "$out/$v-$phase.log"
    done
done
