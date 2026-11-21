#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 || $# == 2 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT [COMPOSED_DESKTOP]' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
composed=""
if (( $# == 2 )); then composed=$(realpath "$2"); fi
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
p=src/ui/chat
files=("$p/history/height_key.rs" "$p/session.rs" "$p/scroller.rs" "$p/scroller/scrollbar/height_store.rs" crates/tabs LICENSE-GPL LICENSE-APACHE)
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
if [[ -z $composed ]]; then
    git -C "$repo" archive "$base" "${files[@]}" | tar xf -
    echo '=== pinned standalone Desktop ==='
else
    (cd "$composed"; tar cf - "${files[@]}") | tar xf -
    cmp upstream.lock "$composed/Cargo.lock"
    git -C "$repo" show "$base:$p/history/height_key.rs" | cmp - "$p/history/height_key.rs"
    echo '=== cumulative Desktop source and pinned lock ==='
fi
git add src crates/tabs
git apply --check --index "$here/source.patch"
python3 "$here/extract.py" stock
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --config skip_children=true --check "$p/history/height_key.rs" "$here/probe.rs"
python3 "$here/extract.py" candidate
cp "$here/harness.toml" Cargo.toml
cp "$here/harness.lock" Cargo.lock
cp "$here/probe.rs" src/main.rs
printf 'pub(crate) mod chat;\n' > src/ui/mod.rs
cat > src/ui/chat/history/mod.rs <<'RS'
mod stock_key;
mod candidate_key;
use super::{scroller::HeightCacheKey, Session};
use proteus_contracts::app_protocol::AppTranscriptCursor;

pub(crate) fn baseline(session: &Session,cursor:&AppTranscriptCursor)->Option<HeightCacheKey> {
    stock_key::key(session,cursor)
}
pub(crate) fn candidate(session: &Session,cursor:&AppTranscriptCursor)->Option<HeightCacheKey> {
    candidate_key::key(session,cursor)
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
assert any(p[:2]==('sha2','0.10.9') for p in subset)
assert any(p[:2]==('uuid','1.28.0') for p in subset)
print(f"PASS {len(subset)} exact Desktop lock identities including pinned contracts, SHA-256, UUID and real tabs source")
PY
if [[ ! -v CARGO_TARGET_DIR ]]; then export CARGO_TARGET_DIR="$w/target"; fi
rustc --version
echo "Base $base"
sha256sum "$here/source.patch" | sed 's@  .*@  source.patch@'
echo 'PASS full stock/candidate key, durable-id accessor, key fields and SHA helper extracted with minimal non-GPUI session shell'
name=desktop-warm-history-height-identity-probe
bin="$CARGO_TARGET_DIR/debug/$name"
touch src/ui/chat/history/candidate_key.rs
cargo test --offline --locked -j1 --bin "$name" | tee focused-tests.log
grep -q 'geometry_identity_keeps_the_legacy_formatted_preimage.*ok' focused-tests.log
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
assert len(alloc)==5
for name, arms in alloc.items():
    a,b=arms['stock'],arms['candidate']
    if name=='unidentified-chat':
        assert a==b==(0,0)
    else:
        assert a[0]>b[0] and a[1]>b[1]
    print(f'{name} requests/bytes {a} -> {b}')
PY
