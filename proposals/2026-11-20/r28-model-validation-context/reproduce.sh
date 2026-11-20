#!/usr/bin/env bash
# Usage: bash reproduce.sh /absolute/path/to/Proteus-core /absolute/path/to/proteus-jsonl-session-storage-module /new/output/directory
set -eu -o pipefail
here=$(cd "$(dirname "$0")"; pwd)
base=048378da7cbe890d8bf8a0152e55eb28ecb5013d
[[ $# == 3 && -x "$2" ]] || { echo 'Need Core checkout, stock JSONL worker executable and an unused output directory' >&2; exit 2; }
src=$(realpath "$1"); export PROTEUS_TEST_SESSION_STORAGE_MODULE=$(realpath "$2")
mkdir "$3"; out=$(realpath "$3"); git clone --quiet --no-checkout "$src" "$out/src"
cd "$out/src"; git checkout --quiet --detach "$base"
export CARGO_TARGET_DIR="$out/target"
cargo fmt --all -- --check
git apply --check "$here/validation-context.patch"
git apply "$here/alloc-probe.patch"
cargo test --locked -p proteus-core --lib r28_ -- --test-threads=1 --nocapture 2>&1 | tee "$out/baseline.log"
git apply "$here/validation-context.patch"
cargo fmt --all -- --check
cargo test --locked -p proteus-core --lib r28_ -- --test-threads=1 --nocapture 2>&1 | tee "$out/candidate.log"
python3 "$here/compare.py" "$out/baseline.log" "$out/candidate.log"
for scope in core::model_service::tests:: core::prompt_replay::tests::; do
  cargo test --locked -p proteus-core --lib "$scope" -- --test-threads=1
done
