#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
git -C "$repo" archive "$base" src/ui/settings/tags.rs src/ui/settings/tags | tar xf -
git -C "$repo" show "$base:Cargo.lock" > original.lock
git add src
git apply --index --check "$here/source.patch"
python3 "$here/extract.py" src/ui/settings src/stock.rs
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --config skip_children=true --check \
    src/ui/settings/tags.rs src/ui/settings/tags/{editor,suggest,tests}.rs "$here/probe.rs"
cp src/ui/settings/tags/suggest.rs src/candidate.rs
cp "$here/harness.toml" Cargo.toml
cp "$here/harness.lock" Cargo.lock
cp "$here/probe.rs" src/main.rs
python3 - <<'PY'
import tomllib
def deps(p):
    with open(p, 'rb') as f:
        return {(x['name'],x['version'],x['source'],x.get('checksum')) for x in tomllib.load(f)['package'] if 'source' in x}
part=deps('Cargo.lock')
assert part <= deps('original.lock')
assert any(p[0]=='proteus-contracts' and p[2].endswith('#7cbc7206f03fac130d05bed2844de275476fedc8') for p in part)
print(f"PASS {len(part)} dependency identities match the Desktop lock, incl. exact contracts Git commit")
PY
if [[ ! -v CARGO_TARGET_DIR ]]; then export CARGO_TARGET_DIR="$w/target"; fi
rustc --version
echo "Base $base"
sha256sum "$here/source.patch" | sed 's@  .*@  source.patch@'
cargo test --offline --locked -j2 --bin desktop-tag-suggest-probe
cargo build --offline --locked -j2 --features count
bin="$CARGO_TARGET_DIR/debug/desktop-tag-suggest-probe"
for arm in stock candidate; do "$bin" "$arm" | tee -a alloc.tsv; done
cargo build --offline --locked -j2
"$bin" parity
for ((i=0;i<8;i++)); do
    if ((i%2)); then first=candidate; second=stock; else first=stock; second=candidate; fi
    for arm in "$first" "$second"; do "$bin" "$arm" | tee -a runs.tsv; done
done
python3 - <<'PY'
from collections import defaultdict
from pathlib import Path
from statistics import median
alloc=defaultdict(dict); times=defaultdict(lambda:defaultdict(list))
for line in Path('alloc.tsv').read_text().splitlines():
    tag,arm,name,calls,requested=line.split('\t')
    assert tag=='alloc'
    alloc[name][arm]=(int(calls),int(requested))
for line in Path('runs.tsv').read_text().splitlines():
    tag,arm,name,ns=line.split('\t')
    assert tag=='time'
    times[name][arm].append(float(ns)/1000)
assert len(alloc)==len(times)==4
for name in ('24-open','24-type','80-miss','512-open'):
    a,b=(alloc[name][v] for v in ('stock','candidate'))
    x,y=(times[name][v] for v in ('stock','candidate'))
    assert len(x)==len(y)==8
    assert b[1]<a[1],(name,a,b)
    print(f'{name} requests/bytes {a} -> {b}; median {median(x):.3f} -> {median(y):.3f} us')
PY
