#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
git -C "$repo" archive "$base" src/transcript src/agents/codex/types.rs src/ui/chat/{tool_chain,tool_row,thread}.rs | tar xf -
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
git add src
git apply --check --index "$here/source.patch"
python3 - <<'PY'
from pathlib import Path
root=Path('src/ui/chat')
def read(name):
    return (root/name).read_text()
chain=read('tool_chain.rs')
thread=read('thread.rs')
tool_row=read('tool_row.rs')
begin=thread.index('                    let tools: Vec<_> = entries[chain.clone()]')
end=thread.index('                    let header =',begin)
collect=thread[begin:end]
start=chain.index('    let mut labels: Vec<(&str, usize)>')
end=chain.index('    let weak =',start)
labels=chain[start:end]
start=chain.index('fn chain_status(')
status=chain[start:]
start=tool_row.index('pub(super) fn is_running(')
end=tool_row.index('\n}\n',start)+3
runner=tool_row[start:end]
Path('is_running.extracted').write_text(runner)
Path('stock.extracted').write_text('''use super::super::tool_row::is_running;
use crate::transcript::Entry;
use proteus_contracts::app_protocol::AppTranscriptTool;
use std::ops::Range;
pub fn summarize(entries: &[Entry], chain: Range<usize>) -> (usize, &'static str, Vec<(&str, usize)>) {
'''+collect+'    let tools = &tools;\n'+labels+'    (tools.len(), chain_status(tools), labels)\n}\n\n'+status)
print('PASS extracted unchanged stock reference collection, label fold, status checks and running predicate')
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
rustfmt --edition 2024 --config skip_children=true --check src/ui/chat/{thread,tool_chain}.rs src/ui/chat/tool_chain/summary.rs "$here/probe.rs"
# Use stock is_running verbatim and retain the summary module's actual path,
# with only the GUI wrapper replaced by a thin projection entry point.
mv is_running.extracted src/ui/chat/tool_row.rs
mv stock.extracted src/ui/chat/tool_chain/stock.rs
printf 'pub mod chat;\n' > src/ui/mod.rs
printf 'pub mod tool_chain;\nmod tool_row;\n' > src/ui/chat/mod.rs
cat > src/ui/chat/tool_chain.rs <<'RS'
pub mod stock;
mod summary;
use crate::transcript::Entry;
use std::ops::Range;

pub fn candidate(entries: &[Entry], chain: Range<usize>) -> (usize, &'static str, Vec<(&str, usize)>) {
    let tools = entries[chain].iter().filter_map(|entry| entry.tool.as_ref());
    let summary::Summary { count, status, labels } = summary::summarize(tools);
    (count, status, labels)
}
RS
echo '=== original transcript and candidate header summary ==='
name=desktop-folded-tool-summary-probe
bin="$CARGO_TARGET_DIR/debug/$name"
touch src/ui/chat/tool_chain/summary.rs
cargo test --offline --locked -j1 --bin "$name" | tee focused-tests.log
grep -q 'repeated_labels_keep_first_order_while_approval_uses_highest_priority.*ok' focused-tests.log
cargo build --offline --locked -j1
"$bin" parity
for arm in stock candidate; do "$bin" "$arm" > "$arm.alloc"; done
python3 - <<'PY'
from pathlib import Path
def alloc(arm):
    data={}
    for row in Path(arm+'.alloc').read_text().splitlines():
        tag,name,calls,requested=row.split('\t')
        assert tag=='alloc'
        data[name]=int(calls),int(requested)
    return data
stock,candidate=(alloc(arm) for arm in ('stock','candidate'))
assert stock.keys()==candidate.keys() and len(stock)==4
for name, both in stock.items():
    after=candidate[name]
    if name.endswith('-control'):
        assert both==after==(0,0)
    else:
        assert after[0]<both[0] and after[1]<both[1]
    print(f'{name} requests/bytes {both} -> {after}')
PY
