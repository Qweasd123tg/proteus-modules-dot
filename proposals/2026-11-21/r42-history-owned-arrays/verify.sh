#!/usr/bin/env bash
# Read-only input: exact upstream sdk/src/ui.rs and a compatible serde_json rlib.
set -euo pipefail
if [[ $# != 2 ]]; then echo "usage: bash verify.sh /path/to/stock/sdk/src/ui.rs /path/to/deps/libserde_json-HASH.rlib" >&2; exit 2; fi
here=$(cd "$(dirname "$0")" && pwd)
ui=$(realpath "$1")
deps=$(cd "$(dirname "$2")" && pwd)
serde="$deps/$(basename "$2")"
rustc=${RUSTC:-rustc}
test -f "$serde"
test "$(git hash-object "$ui")" = ea9f40af6aab1eccc26bcd448ea567c94042212b
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
git init -q
mkdir -p sdk/src
cp "$ui" sdk/src/ui.rs
cp "$here/probe.rs" sdk/src/probe.rs
flags=(--edition 2024 -C opt-level=3 -C strip=symbols -L "dependency=$deps" --extern "serde_json=$serde")
git apply --check "$here/source.patch"
for phase in stock candidate; do
    if [[ $phase == candidate ]]; then git apply "$here/source.patch"; fi
    "$rustc" "${flags[@]}" sdk/src/probe.rs -o probe
    ./probe > "$phase.jsonl" 2> "$phase.tsv"
    "$rustc" "${flags[@]}" --test sdk/src/ui.rs -o tests
    ./tests
done
cmp stock.jsonl candidate.jsonl
echo 'Byte-identical output:'; sha256sum candidate.jsonl
echo 'widget rows alloc_calls requested_B extra_peak_live_B'
cat stock.tsv
echo 'Patched:'
cat candidate.tsv
git apply --check -R "$here/source.patch"
git apply -R "$here/source.patch"
cmp sdk/src/ui.rs "$ui"
