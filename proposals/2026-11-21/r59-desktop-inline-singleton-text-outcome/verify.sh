#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
git -C "$repo" archive "$base" src/transcript src/agents/codex/types.rs | tar xf -
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
git add src
git apply --check --index "$here/source.patch"
cp "$here/harness.toml" Cargo.toml
cp "$here/harness.lock" Cargo.lock
cp "$here/probe.rs" src/main.rs
cat > src/agents/codex/mod.rs <<'RS'
mod types;
pub use types::{Item, ItemKind};
RS
python3 - <<'PY'
import tomllib
def packages(file):
    with open(file,'rb') as f:
        return [r for r in tomllib.load(f)['package'] if 'source' in r]
def ids(p):
    return {(r['name'],r['version'],r['source'],r.get('checksum')) for r in p}
p=packages('Cargo.lock')
assert ids(p) <= ids(packages('upstream.lock'))
assert any(r['name']=='proteus-contracts' and r['source'].endswith('#7cbc7206f03fac130d05bed2844de275476fedc8') for r in p)
assert any(r['name']=='serde_json' and 'indexmap' in r['dependencies'] for r in p)
print(f"PASS {len(p)} exact Desktop lock identities including pinned contracts and serde_json preserve_order")
PY
if [[ ! -v CARGO_TARGET_DIR ]]; then export CARGO_TARGET_DIR="$w/target"; fi
rustc --version
echo "Base $base"
sha256sum "$here/source.patch" | sed 's@  .*@  source.patch@'
name=desktop-singleton-text-outcome-probe
bin="$CARGO_TARGET_DIR/debug/$name"
new_case=a_run_reduced_to_one_event_keeps_its_effect_and_timestamp
echo '=== stock transcript ==='
touch src/transcript/text_run.rs src/transcript/text_run/tests.rs
cargo test --offline --locked -j1 --bin "$name" | tee stock-tests.log
if grep -q "$new_case" stock-tests.log; then
    echo 'stale candidate test binary in stock arm' >&2; exit 1
fi
cargo build --offline --locked -j1
"$bin" parity > stock.trace
"$bin" alloc > stock.alloc
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --check src/transcript/text_run.rs
rustfmt --edition 2024 --config skip_children=true --check "$here/probe.rs"
echo '=== candidate transcript ==='
touch src/transcript/text_run.rs src/transcript/text_run/tests.rs
cargo test --offline --locked -j1 --bin "$name" | tee candidate-tests.log
grep -q "$new_case.*ok" candidate-tests.log
cargo build --offline --locked -j1
"$bin" parity > candidate.trace
"$bin" alloc > candidate.alloc
cmp stock.trace candidate.trace
command sha256sum stock.trace candidate.trace
wc -l stock.trace candidate.trace
python3 - <<'PY'
from pathlib import Path
cases=4*2*9**3*8
assert Path('candidate.trace').read_text().splitlines()[-1] == f'parity cases\t{cases}'
print(f'PASS {cases} byte-identical event/layout/visibility/retained-row cases')
def scan(arm):
    rows=Path(arm+'.alloc').read_text().splitlines()
    alloc={}
    outcomes={}
    for row in rows:
        tag,name,*rest=row.split('\t')
        if tag=='inline-size':
            print(f'{arm} TextRunOutcome inline size {name} B')
        if tag=='alloc':
            alloc[name]=tuple(map(int,rest))
        elif tag=='outcome': outcomes[name]=tuple(rest)
    return alloc,outcomes
stock, old_outcomes=scan('stock')
candidate, new_outcomes=scan('candidate')
assert old_outcomes==new_outcomes
assert stock.keys()==candidate.keys() and len(stock)==8
for name, old in stock.items():
    new=candidate[name]
    if name.startswith('singleton-') or name=='filtered-to-one':
        assert old[0]-new[0]==1 and old[1]-new[1]>=1,(name,old,new)
    else: assert old==new,(name,old,new)
    print(f'{name} requests/bytes {old} -> {new}')
PY
