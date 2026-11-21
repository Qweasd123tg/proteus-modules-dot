#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
p=src/agents/codex/projection.rs
git -C "$repo" archive "$base" src/agents/codex/{types,projection,mod}.rs | tar xf -
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
git add src
git apply --check --index "$here/source.patch"
cp "$p" src/agents/codex/stock.rs
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --config skip_children=true --check "$p" "$here/probe.rs"
cp "$here/harness.toml" Cargo.toml
cp "$here/harness.lock" Cargo.lock
cp "$here/probe.rs" src/main.rs
python3 - <<'PY'
from pathlib import Path
module=Path('src/agents/codex/mod.rs')
src=module.read_text()
begin=src.index('                projection::item(')
end=src.index('            })',begin)
history=src[begin:end].strip()
assert '.get("turnId")' in history and "entry.get(\"startedAtMs\")" in history
module.write_text('''mod types;
pub use types::*;
pub mod stock;
pub mod projection;
use serde_json::Value;
pub type ValueProjection = fn(&str, &Value) -> Option<Event>;

pub fn parity_clip(text: &str) {
    let old = stock::clipped(text);
    let new = projection::clipped(text);
    assert!(old == new);
    assert!(new.capacity() <= old.capacity());
}

pub fn parity_history(entry: &Value) {
    let old = '''+history.replace('projection::','stock::',1)+''';
    let new = '''+history+''';
    assert!(old == new);
    if let (Some(old), Some(new)) = (old, new) {
        assert_eq!(new.turn_id.capacity(), old.turn_id.capacity());
    }
}
''')
PY
python3 - <<'PY'
import tomllib
def packages(file):
    with open(file,'rb') as f:
        return {(r['name'],r['version'],r['source'],r.get('checksum')) for r in tomllib.load(f)['package'] if 'source' in r}
subset=packages('Cargo.lock')
assert subset <= packages('upstream.lock')
assert any(p[0]=='serde_json' and p[1]=='1.0.152' for p in subset)
print(f"PASS {len(subset)} exact Desktop lock identities, including serde_json 1.0.152")
PY
if [[ ! -v CARGO_TARGET_DIR ]]; then export CARGO_TARGET_DIR="$w/target"; fi
rustc --version
echo "Base $base"
sha256sum "$here/source.patch" | sed 's@  .*@  source.patch@'
echo 'PASS exact Codex projection/types and historical borrowed-call expression extracted'
name=desktop-codex-item-turn-projection-probe
bin="$CARGO_TARGET_DIR/debug/$name"
touch "$p"
cargo test --offline --locked -j1 --bin "$name" | tee focused-tests.log
grep -q 'projection::tests::upsert_keeps_the_same_bounded_turn_id_and_started_or_completed_stamp.*ok' focused-tests.log
cargo build --offline --locked -j1
"$bin" parity
for arm in stock candidate; do "$bin" "$arm" > "$arm.alloc"; done
python3 - <<'PY'
from collections import defaultdict
from pathlib import Path
alloc=defaultdict(dict)
for arm in ('stock','candidate'):
    for row in Path(arm+'.alloc').read_text().splitlines():
        tag,returned_arm,name,calls,requested=row.split('\t')
        assert tag=='alloc' and returned_arm==arm
        alloc[name][arm]=int(calls),int(requested)
assert len(alloc)==6
for name, arms in alloc.items():
    a,b=arms['stock'],arms['candidate']
    if name in ('assistant-start','command-completion','long-turn-id'):
        assert a[0]>b[0] and a[1]>b[1]
    else:
        assert a==b
    print(f'{name} requests/bytes {a} -> {b}')
PY
