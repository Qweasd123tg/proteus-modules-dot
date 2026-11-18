#!/usr/bin/env bash
# Usage: bash reproduce.sh /path/to/Proteus-core NEW_RESULTS_DIR [commit]
set -euo pipefail
repo=${1:?expected an existing Proteus-core checkout}
output=${2:?expected a new output directory}
pin=${3:-8ea2cdaf4195ae24e941354f68d4e97335d139d7}
bundle=$(cd "$(dirname "$0")" && pwd)
git -C "$repo" cat-file -e "$pin^{commit}"
mkdir "$output"
output=$(cd "$output" && pwd)
git clone --quiet --no-checkout -- "$repo" "$output/tree"
git -C "$output/tree" checkout --quiet --detach "$pin"
cd "$output/tree"
p=crates/proteus-core/src/core/session_store/remote/snapshot.rs
t=crates/proteus-core/src/core/session_store/remote/view/tests.rs
test "$(git hash-object "$p")" = "672939d0442eb51db9cf0471965de71328e4a463"
printf '\n' >> "$t"
cat "$bundle/open-resume-peak-probe.rs" >> "$t"
export CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=3 CARGO_PROFILE_DEV_DEBUG=0 RUSTFLAGS='-C debuginfo=0'
export CARGO_TARGET_DIR="$output/target"
for version in candidate baseline; do
    if test "$version" = candidate; then
        git apply --check --whitespace=error "$bundle/move-validated-history.patch"
        git apply --whitespace=error "$bundle/move-validated-history.patch"
        test "$(git hash-object "$p")" = "ff4f9261a520a35d67f0c9c2759eb808e089f35b"
    else
        git apply -R --check --whitespace=error "$bundle/move-validated-history.patch"
        git apply -R --whitespace=error "$bundle/move-validated-history.patch"
        test "$(git hash-object "$p")" = "672939d0442eb51db9cf0471965de71328e4a463"
    fi
    cargo test --locked -p proteus-core --lib 'session_store::remote::view::tests' -- --test-threads=1 2>&1 | tee "$output/$version-tests.log"
    cargo test --locked -p proteus-core --lib measure_validated_remote_open -- --ignored --nocapture --test-threads=1 2>&1 | tee "$output/$version-probe.log"
    grep -q '6 passed; 0 failed' "$output/$version-tests.log"
    grep -q '1 passed; 0 failed' "$output/$version-probe.log"
done
