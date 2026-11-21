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
python3 - <<'PY'
from pathlib import Path
src=Path('src/transcript/subagent.rs').read_text()
assert 'serde_json::from_value(tool.metadata.get("subagent_session")?.clone()).ok()?' in src
prefix, tests = src.split('#[cfg(test)]', 1)
assert 'fn canonical_task_link_requires_typed_reserved_metadata_not_name_or_uuid' in tests
Path('src/stock.rs').write_text(prefix)
PY
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
echo '=== stock original transcript ==='
touch src/transcript/subagent.rs
cargo test --offline --locked -j1 --bin desktop-child-metadata-probe | tee stock-tests.log
if grep -q 'typed_child_link_still_rejects_malformed_metadata' stock-tests.log; then
    echo 'stale candidate test binary in stock arm' >&2
    exit 1
fi
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --check src/transcript/subagent.rs
rustfmt --edition 2024 --config skip_children=true --check "$here/probe.rs"
echo '=== candidate transcript ==='
touch src/transcript/subagent.rs
cargo test --offline --locked -j1 --bin desktop-child-metadata-probe | tee candidate-tests.log
grep -q 'typed_child_link_still_rejects_malformed_metadata.*ok' candidate-tests.log
cargo build --offline --locked -j1
bin="$CARGO_TARGET_DIR/debug/desktop-child-metadata-probe"
"$bin" parity
for arm in stock candidate; do "$bin" "$arm" | tee -a alloc.tsv; done
python3 - <<'PY'
from collections import defaultdict
from pathlib import Path
alloc=defaultdict(dict)
for line in Path('alloc.tsv').read_text().splitlines():
    tag,arm,name,calls,requested=line.split('\t')
    assert tag=='alloc'
    alloc[name][arm]=(int(calls),int(requested))
assert len(alloc)==7
constant={'missing-binding','null-binding','non-task-tool'}
for name,arms in alloc.items():
    a,b=(arms[v] for v in ('stock','candidate'))
    if name in constant:
        assert b==a,(name,a,b)
    else:
        assert b[0]<a[0] and b[1]<a[1],(name,a,b)
    print(f'{name} requests/bytes {a} -> {b}')
PY
