#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
p=src/ui/chat
git -C "$repo" archive "$base" "$p/session.rs" "$p/tool_row.rs" "$p/feedback" | tar xf -
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
git add src
git apply --check --index "$here/source.patch"
python3 "$here/extract.py" "$p" src/stock stock
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --config skip_children=true --check "$p/session.rs" "$p/feedback/mod.rs" "$p/feedback/tests.rs" "$here/probe.rs"
python3 "$here/extract.py" "$p" src/candidate candidate
cp "$here/harness.toml" Cargo.toml
cp "$here/harness.lock" Cargo.lock
cp "$here/probe.rs" src/main.rs
python3 - <<'PY'
from pathlib import Path
import tomllib
tool=Path('src/ui/chat/tool_row.rs').read_text()
i=tool.index('pub(super) fn is_running(')
j=tool.index('\n}\n',i)+3
Path('src/tool_row.rs').write_text(tool[i:j])
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
echo 'PASS exact feedback modules and session snapshot projection, excluding native widget and history update'
name=desktop-snapshot-receipt-lookup-probe
bin="$CARGO_TARGET_DIR/debug/$name"
touch src/candidate/mod.rs
cargo test --offline --locked -j1 --bin "$name" | tee focused-tests.log
grep -q 'candidate::tests::reconnect_looks_up_only_known_send_ids_not_already_matched_by_run.*ok' focused-tests.log
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
assert len(alloc)==8
for name, arms in alloc.items():
    a,b=arms['stock'],arms['candidate']
    if name == 'empty':
        assert a==b
    else:
        assert a[0]>b[0] and a[1]>b[1]
    print(f'{name} requests/bytes {a} -> {b}')
PY
