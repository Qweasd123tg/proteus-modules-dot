#!/usr/bin/env bash
# Usage: bash reproduce.sh /absolute/Proteus-core /new/result-directory
set -eu -o pipefail
here=$(cd "$(dirname "$0")"; pwd)
src=$(realpath "$1"); mkdir "$2"; out=$(realpath "$2")
git clone --quiet --no-checkout "$src" "$out/core"
cd "$out/core"; git checkout --quiet --detach 048378da7cbe890d8bf8a0152e55eb28ecb5013d
export CARGO_TARGET_DIR="$out/target" CARGO_BUILD_JOBS=1
git apply --check "$here/estimate-ids.patch"
# Compile the actual private ModelService as an ordinary module in an example.
# This is test instrumentation in the disposable checkout, not a runtime patch.
sed -e 's|MODEL_FILE|"../src/core/model_service.rs"|' \
    -e 's|ALLOC_FILE|"../../proteus-contracts/src/test_alloc.rs"|' \
    "$here/probe.rs.in" > crates/proteus-core/examples/r28_estimate_probe.rs
cargo run --locked -p proteus-core --example r28_estimate_probe > "$out/stock.txt"
git apply "$here/estimate-ids.patch"
cargo run --locked -p proteus-core --example r28_estimate_probe > "$out/candidate.txt"
python3 "$here/compare.py" "$out/stock.txt" "$out/candidate.txt"
cargo test --locked -p proteus-contracts --lib model_standard::input_estimates::tests::
cargo test --locked -p proteus-core --test model_process input_estimate:: -- --test-threads=1
