#!/usr/bin/env bash
# Uses a pruned lock corresponding to Desktop's original registry package versions.
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
tree=src/ui/chat/scroller/scrollbar
git -C "$repo" archive "$base" "$tree/height_map.rs" "$tree/height_map" "$tree/height_store.rs" "$tree/height_store" | tar xf -
git add src
git apply --check --index "$here/source.patch"
git -C "$repo" show "$base:Cargo.lock" > original.lock
cp "$here/harness.toml" Cargo.toml
cp "$here/harness.lock" Cargo.lock
python3 - <<'PY'
from pathlib import Path
import tomllib
def packages(p):
    return {
        (d['name'], d['version'], d['source'], d.get('checksum'))
        for d in tomllib.loads(Path(p).read_text())['package'] if 'source' in d
    }
assert packages('Cargo.lock') <= packages('original.lock')
print('PASS all resolved dependencies match the pinned Desktop lock (source, version, checksum)')
PY
cat > src/lib.rs <<'RS'
#![allow(dead_code)]
const APP_ID: &str = "proteus-r46-height-store-probe";
mod ui;
RS
printf 'mod chat;\n' > src/ui/mod.rs
printf 'mod scroller;\n' > src/ui/chat/mod.rs
printf 'mod scrollbar;\n' > src/ui/chat/scroller/mod.rs
printf 'mod height_map;\nmod height_store;\n' > "$tree/mod.rs"
cp "$here/probe.rs" "$tree/height_store/probe.rs"
printf '\n#[cfg(test)]\n#[path = "height_store/probe.rs"]\nmod probe;\n' >> "$tree/height_store.rs"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$w/cargo-target}"
rustc --version
for arm in stock candidate; do
    if [[ $arm == candidate ]]; then
        git apply "$here/source.patch"
        git apply --reverse --check "$here/source.patch"
        git diff --check
        rustfmt --edition 2024 --check "$tree/height_store/"{disk,tests}.rs
    fi
    echo "=== $arm at $base ==="
    cargo test --lib --release --offline --locked --no-run --message-format=json > build.jsonl
    path=$(python3 - <<'PY'
import json
with open('build.jsonl') as f:
    (name,) = (j['executable'] for j in map(json.loads,f) if j['reason']=='compiler-artifact' and j.get('executable') and j['profile']['test'])
print(name)
PY
)
    cp "$path" "$arm"
    ./"$arm" --test-threads=1
done
for ((i=0; i<12; i++)); do
    arms=(stock candidate)
    if ((i % 2)); then arms=(candidate stock); fi
    for arm in "${arms[@]}"; do
        ./"$arm" --ignored --nocapture real_load_probe | awk -v arm="$arm" '{at=index($0,"R46\t"); if (at) print arm "\t" substr($0,at)}' | tee -a runs.tsv
    done
done
python3 - <<'PY'
import csv, statistics
from collections import defaultdict
data=defaultdict(lambda:defaultdict(list))
for arm, label, name, count, keep, cap, retained, t in csv.reader(open('runs.tsv'), delimiter='\t'):
    assert label=='R46'
    data[name,int(count),int(keep)][arm].append(tuple(map(int,(cap,retained,t))))
assert len(data)==5
for (case,count,keep), arms in data.items():
    a,b=[arms[arm] for arm in ('stock','candidate')]
    assert len(a)==len(b)==12
    assert all(cap==count for cap,_,_ in a)
    assert all(cap==keep for cap,_,_ in b)
    a_us,b_us=[statistics.median(s[2] for s in results)/1000 for results in (a,b)]
    print(f'{case}: {a_us:.2f} -> {b_us:.2f} us; retained Vec bytes {a[0][1]} -> {b[0][1]}')
PY
