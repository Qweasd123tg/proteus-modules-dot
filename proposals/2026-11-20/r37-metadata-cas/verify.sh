#!/usr/bin/env bash
# Usage: bash verify.sh /path/to/Proteus-modules; Cargo target may be reused.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$1" && pwd)
base=9469e3b12529d08b1f4a76882693e2065e842c51
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
git clone -q --local --no-checkout "$repo" "$work/repo"
cd "$work/repo"
git checkout -q --detach "$base"
if [[ -z "$(printenv CARGO_TARGET_DIR || :)" ]]; then export CARGO_TARGET_DIR="$work/target"; fi
git apply --check "$here/source.patch"
cp "$here/allocation_probe.rs" storage/session-storage/src/r37_probe.rs
printf '\n#[cfg(test)]\nmod r37_probe;\n' >>storage/session-storage/src/lib.rs
run_probe() {
    cargo test --locked -p session-storage --lib compare_metadata_allocations_and_persisted_bytes -- --test-threads=1 --nocapture >"$1"
    sed -n 's/^.*CAS,/CAS,/p' "$1"
}
run_probe "$work/before.log"
git apply "$here/source.patch"
git diff --check
run_probe "$work/after.log"
python3 - "$work/before.log" "$work/after.log" <<'PY'
import sys
from pathlib import Path
def rows(path):
    return [s.partition('CAS,')[2].split(',') for s in Path(path).read_text().splitlines() if 'CAS,' in s]
a,b=map(rows,sys.argv[1:])
assert len(a)==len(b)==27
for old,new in zip(a,b):
    assert old[:3]==new[:3] and old[5:]==new[5:]
    print(f"{old[0]}, {old[1]} bytes, pass {old[2]}: requested {old[4]} -> {new[4]}")
PY
cargo test --locked -p session-storage -p proteus-session-storage-module -- --test-threads=2
