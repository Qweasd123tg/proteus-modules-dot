#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
git -C "$repo" archive "$base" src/sessions.rs src/conversations.rs src/agents/codex/types.rs crates/tabs LICENSE-GPL LICENSE-APACHE | tar xf -
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
git add src crates/tabs
git apply --index --check "$here/source.patch"
python3 "$here/extract.py" src/sessions.rs src/stock.rs
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
from pathlib import Path
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
echo '=== stock graph modules and membership ==='
# An archive preserves its original mtime; a shared warm Cargo target could
# otherwise consider a newer candidate unit-test executable fresh.
touch src/sessions.rs
cargo test --offline --locked -j1 --lib | tee stock-tests.log
if grep -q 'contains_returns_to_siblings_after_a_deep_branch_miss' stock-tests.log; then
    echo 'stale candidate test binary in stock arm' >&2
    exit 1
fi
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --check src/sessions.rs
rustfmt --edition 2024 --config skip_children=true --check "$here/probe.rs"
echo '=== candidate graph modules and membership ==='
touch src/sessions.rs
cargo test --offline --locked -j1 --lib | tee candidate-tests.log
grep -q 'contains_returns_to_siblings_after_a_deep_branch_miss.*ok' candidate-tests.log
cargo build --offline --locked -j1 --features count
bin="$CARGO_TARGET_DIR/debug/desktop-row-membership-probe"
for arm in stock candidate; do "$bin" "$arm" | tee -a alloc.tsv; done
cargo build --offline --locked -j1
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
    times[name][arm].append(float(ns))
assert len(alloc)==len(times)==6
for name,arms in alloc.items():
    a,b=(arms[v] for v in ('stock','candidate'))
    x,y=(times[name][v] for v in ('stock','candidate'))
    assert len(x)==len(y)==8
    if name in ('leaf-match','leaf-miss','chain-6','sidebar-folded-24'):
        assert a[0]>0 and b==(0,0),(name,a,b)
    else: assert b[0]<=a[0] and b[1]<=a[1],(name,a,b)
    print(f'{name} requests/bytes {a} -> {b}; median {median(x):.2f} -> {median(y):.2f} ns')
PY
