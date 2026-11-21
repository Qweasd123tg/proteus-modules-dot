#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
git -C "$repo" archive "$base" src/transcript src/agents/codex/types.rs src/ui/chat/{row_layout,scroller,view,history,stamp}.rs src/ui/chat/scroller/scrollbar.rs | tar xf -
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
git add src
git apply --check --index "$here/source.patch"
python3 - <<'PY'
from pathlib import Path
d=Path('src/ui/chat')
source=(d/'row_layout.rs').read_text()
end=source.index('#[derive(Debug, PartialEq, Eq)]')
(d/'stock.rs').write_text(source[:end])
def excerpt(file, anchor, name, derive=False, prefix=''):
    src=(d/file).read_text()
    a=src.index(anchor)
    b=src.index('\n}\n',a)+3
    if derive:
        a=src.rfind('#[derive(',0,a)
    Path(name).write_text(prefix+src[a:b])
excerpt('history.rs','pub(super) enum Direction','direction.extracted',True)
excerpt('scroller/scrollbar.rs','pub(crate) struct HistoryRange','range.extracted',True)
excerpt('stamp.rs','pub(super) fn hidden','hidden.extracted',prefix='use crate::transcript::Entry;\n')
assert '!incomplete_rows.iter().any(|rows| rows.contains(&ix))' in (d/'scroller.rs').read_text()
print('PASS extracted original row context, hidden-stamp logic and real range/direction definitions')
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
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --config skip_children=true --check src/ui/chat/{row_layout,scroller,view}.rs "$here/probe.rs"
grep -q 'row_context.is_complete(ix)' src/ui/chat/scroller.rs
mv direction.extracted src/ui/chat/history.rs
mv range.extracted src/ui/chat/scroller.rs
mv hidden.extracted src/ui/chat/stamp.rs
printf 'pub mod chat;\n' > src/ui/mod.rs
cat > src/ui/chat/mod.rs <<'RS'
mod history;
mod row_layout;
mod scroller;
mod stamp;
mod stock;
pub(crate) use scroller::HistoryRange;
use crate::transcript::Entry;
use std::ops::Range;

pub fn baseline(entries: &[Entry], compact: bool, range: Option<HistoryRange>) -> Vec<Range<usize>> {
    stock::row_context(entries, compact, range).incomplete_rows()
}

pub fn candidate(entries: &[Entry], compact: bool, range: Option<HistoryRange>) -> impl Fn(usize) -> bool + use<> {
    let row_context = row_layout::row_context(entries, compact, range);
    move |ix| row_context.is_complete(ix)
}
RS
echo '=== original transcript and candidate row context ==='
name=desktop-chat-list-context-probe
bin="$CARGO_TARGET_DIR/debug/$name"
touch src/ui/chat/row_layout.rs
cargo test --offline --locked -j1 --bin "$name" | tee focused-tests.log
grep -q 'layout_measurements_are_incomplete_only_inside_each_clipped_range.*ok' focused-tests.log
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
    stock, candidate = map(arms.__getitem__, ('stock','candidate'))
    if name.startswith('paged-'):
        assert stock[0]-candidate[0]==1 and stock[1]-candidate[1]>0
    else:
        assert stock==candidate==(0,0)
    print(f'{name} requests/bytes {stock} -> {candidate}')
PY
