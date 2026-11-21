#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
git -C "$repo" archive "$base" src/ui/panels/sessions.rs src/sessions.rs src/conversations.rs src/agents/codex/types.rs crates/tabs | tar xf -
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
git add src crates/tabs
git apply --index --check "$here/source.patch"
python3 "$here/extract.py" src/ui/panels/sessions.rs src/stock.rs
cp "$here/harness.toml" Cargo.toml
cp "$here/harness.lock" Cargo.lock
cp "$here/probe.rs" src/main.rs
cat > src/lib.rs <<'RS'
#![allow(dead_code, unused_imports)]
pub mod agents {
    pub mod codex;
}
pub mod conversations;
pub mod sessions;
RS
cat > src/agents/codex/mod.rs <<'RS'
mod types;
pub use types::{Model, Summary};
RS
python3 - <<'PY'
import tomllib
def packages(file):
    with open(file,'rb') as f:
        return {(r['name'],r['version'],r['source'],r.get('checksum')) for r in tomllib.load(f)['package'] if 'source' in r}
subset=packages('Cargo.lock')
assert subset <= packages('upstream.lock')
assert any(p[0]=='proteus-contracts' and p[2].endswith('#7cbc7206f03fac130d05bed2844de275476fedc8') for p in subset)
print(f"PASS {len(subset)} exact Desktop lock identities including contracts Git commit")
PY
if [[ ! -v CARGO_TARGET_DIR ]]; then export CARGO_TARGET_DIR="$w/target"; fi
rustc --version
echo "Base $base"
sha256sum "$here/source.patch" | sed 's@  .*@  source.patch@'
echo '=== stock listing modules ==='
cargo test --offline --locked -j2 --lib
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --config skip_children=true --check \
    src/ui/panels/sessions.rs src/ui/panels/sessions/project_rows.rs "$here/probe.rs"
cp src/ui/panels/sessions/project_rows.rs src/project_rows.rs
printf '\npub mod project_rows;\n' >> src/lib.rs
echo '=== stock listing modules with new project-root visitor ==='
cargo test --offline --locked -j2 --lib
cargo build --offline --locked -j2 --features count
bin="$CARGO_TARGET_DIR/debug/desktop-project-rows-probe"
for arm in stock candidate; do "$bin" "$arm" | tee -a alloc.tsv; done
cargo build --offline --locked -j2
"$bin" parity
for ((i=0;i<8;i++)); do
    if ((i%2)); then first=candidate; second=stock; else first=stock; second=candidate; fi
    for arm in "$first" "$second"; do "$bin" "$arm" | tee -a samples.tsv; done
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
for line in Path('samples.tsv').read_text().splitlines():
    tag,arm,name,ns=line.split('\t')
    assert tag=='time'
    times[name][arm].append(float(ns)/1000)
assert len(alloc)==len(times)==7
for name,arms in alloc.items():
    a,b=(arms[v] for v in ('stock','candidate'))
    x,y=(times[name][v] for v in ('stock','candidate'))
    assert len(x)==len(y)==8
    assert b[0]<a[0] and b[1]<a[1]
    print(f'{name} requests/bytes {a} -> {b}; median {median(x):.3f} -> {median(y):.3f} us')
PY
