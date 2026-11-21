#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
path=src/ui/chat/activity_dock.rs
git -C "$repo" archive "$base" "$path" | tar xf -
git add src
git apply --check --index "$here/source.patch"
python3 "$here/extract.py" "$path" stock.rs stock
git apply "$here/source.patch"
git apply --reverse --check "$here/source.patch"
git diff --check
rustfmt --edition 2024 --config skip_children=true --check "$path" "$here/probe.rs"
python3 "$here/extract.py" "$path" candidate.rs candidate
cp "$here/probe.rs" probe.rs
rustc --version
echo "Base $base"
sha256sum "$here/source.patch" | sed 's@  .*@  source.patch@'
echo 'PASS exact stock and candidate DockState, request kinds, and existing tests extracted without GPUI formatting'
rustc --edition=2024 -C opt-level=2 --test probe.rs -o tests
./tests --test-threads 1 | tee tests.log
grep -q 'candidate::tests::unchanged_render_keeps_collapsed_requests_but_repairs_a_stale_selection.*ok' tests.log
rustc --edition=2024 -C opt-level=2 probe.rs -o probe
./probe parity
for arm in stock candidate; do ./probe "$arm" > "$arm.alloc"; done
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
    if name.startswith('same-'):
        assert a[0]>0 and b==(0,0)
    else:
        assert a==b
    print(f'{name} requests/bytes {a} -> {b}')
PY
