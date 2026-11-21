#!/usr/bin/env bash
# bash verify.sh /path/to/Proteus-modules /path/to/empty-results
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$1" && pwd)
mkdir -p "$2"; out=$(cd "$2" && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
git clone -q --shared --no-checkout "$repo" "$work/repo"
cd "$work/repo"
git checkout -q --detach 9469e3b12529d08b1f4a76882693e2065e842c51
git apply --check "$here/source.patch"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$work/target}" CARGO_INCREMENTAL=0
cp "$here/allocation_probe.rs" storage/session-storage/src/tests/r40_probe.rs
printf '\nmod r40_probe;\n' >> storage/session-storage/src/tests/mod.rs
for variant in before after; do
    if [[ $variant == after ]]; then git apply "$here/source.patch"; fi
    cargo test --locked -p session-storage --lib tests::r40_probe:: -- --test-threads=1 --nocapture >"$out/$variant.log" 2>&1
done
python3 "$here/compare.py" "$out"
