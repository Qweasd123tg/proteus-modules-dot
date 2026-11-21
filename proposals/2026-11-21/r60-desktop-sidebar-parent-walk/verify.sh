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
git apply --check --index "$here/source.patch"
python3 - <<'PY'
from pathlib import Path
text=Path('src/sessions.rs').read_text()
start=text.index('fn break_cycles(')
end=text.index('\n}\n', start)+3
function=text[start:end]
assert 'let mut path = Vec::new();' in function and 'for i in path' in function
Path('src/stock.rs').write_text('pub '+function)
PY
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
cat >> src/sessions.rs <<'RS'

#[doc(hidden)]
pub fn probe_break_cycles(parents: &mut [Option<usize>]) {
    break_cycles(parents);
}
RS
python3 - <<'PY'
import tomllib
def packages(file):
    with open(file,'rb') as f:
        return {(r['name'],r['version'],r['source'],r.get('checksum')) for r in tomllib.load(f)['package'] if 'source' in r}
subset=packages('Cargo.lock')
assert subset <= packages('upstream.lock')
assert any(p[0]=='proteus-contracts' and p[2].endswith('#7cbc7206f03fac130d05bed2844de275476fedc8') for p in subset)
print(f"PASS {len(subset)} exact Desktop lock identities including pinned contracts")
PY
if [[ ! -v CARGO_TARGET_DIR ]]; then export CARGO_TARGET_DIR="$w/target"; fi
rustc --version
echo "Base $base"
sha256sum "$here/source.patch" | sed 's@  .*@  source.patch@'
name=desktop-sidebar-parent-walk-probe
bin="$CARGO_TARGET_DIR/debug/$name"
new_test=cycle_cut_keeps_the_same_edge_when_other_chains_join_it
echo '=== stock sessions and conversations ==='
touch src/sessions.rs
cargo test --offline --locked -j1 --lib | tee stock-tests.log
if grep -q "$new_test" stock-tests.log; then
    echo 'stale candidate test binary in stock arm' >&2; exit 1
fi
cargo build --offline --locked -j1
"$bin" listings > stock.trace
"$bin" alloc > stock.alloc
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --check src/sessions.rs
rustfmt --edition 2024 --config skip_children=true --check "$here/probe.rs"
echo '=== candidate sessions and conversations ==='
touch src/sessions.rs
cargo test --offline --locked -j1 --lib | tee candidate-tests.log
grep -q "$new_test.*ok" candidate-tests.log
cargo build --offline --locked -j1
"$bin" edges
"$bin" listings > candidate.trace
"$bin" alloc > candidate.alloc
cmp stock.trace candidate.trace
command sha256sum stock.trace candidate.trace
python3 - <<'PY'
from pathlib import Path
n=7*5*2*2*5*2
assert Path('candidate.trace').read_text().splitlines()[-1]==f'listing cases\t{n}'
print(f'PASS {n} byte-identical SessionMarks::arrange outputs')
def allocations(arm):
    result={}
    for row in Path(arm+'.alloc').read_text().splitlines():
        tag,name,calls,requested=row.split('\t')
        assert tag=='alloc'
        result[name]=int(calls),int(requested)
    return result
stock, candidate=(allocations(arm) for arm in ('stock','candidate'))
assert stock.keys()==candidate.keys() and len(stock)==10
for name, old in stock.items():
    new=candidate[name]
    if name.endswith('-empty'):
        assert old==new==(0,0),(name,old,new)
    else:
        assert new[0]<old[0] and new[1]<old[1],(name,old,new)
    if name.startswith('listing-'):
        equivalent='parent-'+name.removeprefix('listing-')
        assert tuple(a-b for a,b in zip(old,new)) == tuple(a-b for a,b in zip(stock[equivalent],candidate[equivalent])),name
    print(f'{name} requests/bytes {old} -> {new}')
PY
