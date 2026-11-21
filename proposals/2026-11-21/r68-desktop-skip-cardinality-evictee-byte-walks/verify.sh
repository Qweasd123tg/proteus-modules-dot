#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 || $# == 3 )) || { echo 'usage: bash verify.sh PINNED_DESKTOP_CHECKOUT [COMPOSED_DESKTOP DESKTOP_SOURCE_SEAL]' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
if (( $# == 3 )); then tree=$(realpath "$2"); seal=$(realpath "$3"); fi
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"
p=src/ui/chat
files=(src/transcript src/agents/codex/types.rs "$p/history.rs" "$p/history/context.rs" "$p/history/tests.rs" "$p/row_layout.rs" "$p/stamp.rs" "$p/scroller/scrollbar.rs")
mkdir source
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
if (( $# == 3 )); then
    python3 "$here/seal_check.py" "$tree" "$seal"
    (cd "$tree"; tar cf - "${files[@]}") | tar xf - -C source
    cmp upstream.lock "$tree/Cargo.lock"
else
    git -C "$repo" archive "$base" "${files[@]}" | tar xf - -C source
fi
cd source
git init -q
git add src
git apply --index --check "$here/source.patch"
cd "$w"
for arm in stock candidate; do
    cp -a source "$arm"
    if [[ "$arm" == candidate ]]; then
        git -C "$arm" apply "$here/source.patch"
        git -C "$arm" apply --reverse --check "$here/source.patch"
        git -C "$arm" diff --check
        rustfmt --edition 2024 --config skip_children=true --check "$arm/$p/history.rs"
    fi
    python3 "$here/materialize.py" "$arm"
    cp "$here/harness.toml" "$arm/Cargo.toml"
    cp "$here/harness.lock" "$arm/Cargo.lock"
    cp "$here/probe.rs" "$arm/src/main.rs"
    cp "$here/ledger.rs" "$arm/src/ledger.rs"
    cp "$here/diagnostic.rs" "$arm/$p/history/diagnostic.rs"
done
rustfmt --edition 2024 --config skip_children=true --check "$here/"{probe,ledger,diagnostic}.rs
python3 - <<'PY'
import tomllib
def ids(file):
    with open(file,'rb') as f:
        return {(r['name'],r['version'],r['source'],r.get('checksum')) for r in tomllib.load(f)['package'] if 'source' in r}
subset=ids('stock/Cargo.lock')
assert subset<=ids('upstream.lock')
assert any(p[0]=='proteus-contracts' and p[2].endswith('#7cbc7206f03fac130d05bed2844de275476fedc8') for p in subset)
print(f'PASS {len(subset)} pinned dependency identities including Desktop contracts')
PY
if [[ ! -v CARGO_TARGET_DIR ]]; then export CARGO_TARGET_DIR="$w/target"; fi
rustc --version
echo "Base $base"
sha256sum "$here/source.patch" | sed 's@  .*@  source.patch@'
name=desktop-history-byte-work-probe
bin="$CARGO_TARGET_DIR/debug/$name"
for arm in stock candidate; do
    echo "=== $arm exact history, transcript and semantic context ==="
    (cd "$arm"
      touch src/ui/chat/history.rs
      cargo test --offline --locked -j1 --bin "$name" | tee "../$arm-tests.log"
      cargo build --offline --locked -j1
      "$bin" > "../$arm.trace")
    grep '^parity' "$arm.trace" > "$arm.parity"
    grep '^work' "$arm.trace" > "$arm.work"
done
cmp stock.parity candidate.parity
sha256sum stock.parity candidate.parity
grep 'matrix-cases' candidate.parity
python3 - <<'PY'
from pathlib import Path
def counts(arm):
    return {tuple(x[1:3]):[tuple(map(int,x.split(','))) for x in x[3:]] for row in Path(arm+'.work').read_text().splitlines() if (x:=row.split('\t'))[0]=='work'}
a,b=counts('stock'),counts('candidate')
assert a.keys()==b.keys()
for key in a:
    old,new=a[key],b[key]
    if key[0].startswith('codex-') or key[0].startswith('core-snapshot-') or key[0] in ('core-byte-only','core-large-visible') or key[1]=='core.context.loaded':
        assert old==new,(key,old,new)
    if key[0] in ('core-older-nested','core-older-text','core-newer-nested') and key[1]=='core.trim':
        assert sum(old[0])==300 and sum(new[0])==200,(key,old,new)
        if key[0]!='core-older-text':
            assert sum(old[2])>sum(new[2])>0
    print(f"work {key[0]} {key[1]} visits/distinct/JSON = {old} -> {new}")
print('PASS unchanged logical anchors, retained versions, splice sequences, text lengths and cursors')
PY
if (( $# == 3 )); then python3 "$here/seal_check.py" "$tree" "$seal"; fi
