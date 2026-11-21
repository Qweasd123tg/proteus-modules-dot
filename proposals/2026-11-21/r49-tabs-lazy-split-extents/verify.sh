#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"
git init -q
git -C "$repo" archive "$base" crates/tabs | tar xf -
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
git add crates/tabs
git apply --index --check "$here/source.patch"
mkdir src
cp "$here/probe.rs" src/main.rs
cp "$here/harness.toml" Cargo.toml
cp "$here/harness.lock" Cargo.lock
python3 - <<'PY'
import tomllib
def packages(file):
    with open(file,'rb') as f:
        return {(r['name'],r['version'],r['source'],r.get('checksum')) for r in tomllib.load(f)['package'] if 'source' in r}
subset=packages('Cargo.lock')
assert len(subset)==11 and subset <= packages('upstream.lock')
print("PASS 11 dependency versions, registry identities and checksums match Desktop Cargo.lock")
PY
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$w/target}"
rustc -Vv
uname -sm
sha256sum "$here/source.patch" | sed 's@  .*@  source.patch@'
for arm in stock candidate; do
    if [[ $arm == candidate ]]; then
        git apply "$here/source.patch"
        git apply --reverse --check "$here/source.patch"
        git diff --check
        rustfmt --edition 2024 --check crates/tabs/src/{geometry,lock,size}.rs
    fi
    echo "=== $arm @$base ==="
    cargo test --locked --offline --release -p proteus-tabs
    cargo build --locked --offline --release --features count
    "$CARGO_TARGET_DIR/release/tabs-geometry-probe" "$arm" | tee -a alloc.tsv
    cargo build --locked --offline --release
    cp "$CARGO_TARGET_DIR/release/tabs-geometry-probe" "$arm"
    "./$arm" dump > "$arm.geometry"
done
cmp stock.geometry candidate.geometry
n=$(wc -l <stock.geometry); [[ $n == 1632 ]]
echo "PASS $n layouts × dimensions combinations: exact pane IDs, order and four f32 coordinate bit patterns"
sha256sum stock.geometry candidate.geometry
for ((i=0;i<8;i++)); do
    arms=(stock candidate)
    if ((i%2)); then arms=(candidate stock); fi
    for arm in "${arms[@]}"; do "./$arm" "$arm" | tee -a samples.tsv; done
done
python3 - <<'PY'
from pathlib import Path
from collections import defaultdict
from statistics import median
alloc = defaultdict(dict); times=defaultdict(lambda:defaultdict(list))
for line in Path('alloc.tsv').read_text().splitlines():
    tag,arm,name,*nums=line.split('\t')
    assert tag=='alloc'
    alloc[name][arm]=[int(v) for v in nums]
for line in Path('samples.tsv').read_text().splitlines():
    tag,arm,name,v=line.split('\t')
    assert tag=='time'
    times[name][arm].append(float(v))
assert len(alloc)==len(times)==5
for name,arms in alloc.items():
    sa,ea,a,b=arms['stock']; sc,ec,c,d=arms['candidate']
    assert (sa,ea)==(sc,ec) and a-c==sa and b-d==4*ea, (name,arms)
    x,y=(times[name][n] for n in ('stock','candidate'))
    assert len(x)==len(y)==8
    print(f'{name} splits={sa}; calls/bytes {a}/{b} -> {c}/{d}; median ns/call {median(x):.2f} -> {median(y):.2f}')
PY
