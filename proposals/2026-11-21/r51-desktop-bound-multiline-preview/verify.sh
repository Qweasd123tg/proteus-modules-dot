#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
git -C "$repo" archive "$base" src/tool_display | tar xf -
git -C "$repo" show "$base:Cargo.lock" > original.lock
git add src
git apply --index --check "$here/source.patch"
cp "$here/harness.toml" Cargo.toml
cp "$here/harness.lock" Cargo.lock
cp "$here/probe.rs" src/main.rs
cat > src/lib.rs <<'RS'
pub mod tool_display;
RS
python3 - <<'PY'
import tomllib
def deps(name):
    with open(name, 'rb') as f:
        return {(x['name'],x['version'],x['source'],x.get('checksum')) for x in tomllib.load(f)['package'] if 'source' in x}
assert deps('Cargo.lock') <= deps('original.lock')
print('PASS all dependency versions/sources/checksums match the Desktop lock')
PY
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$w/target}"
rustc --version
sha256sum "$here/source.patch" | sed "s|  .*$|  source.patch|"
for arm in stock candidate; do
    if [[ $arm == candidate ]]; then
        git apply "$here/source.patch"
        git apply --reverse --check "$here/source.patch"
        git diff --check
        rustfmt --edition 2024 --check src/tool_display/{mod,tests}.rs
    fi
    echo "=== $arm @$base ==="
    cargo test --offline --locked --release --lib -- --test-threads=1
    cargo test --offline --locked --release --lib --features preserve_order -- --test-threads=1
    cargo build --offline --locked --release --features preserve_order
    "$CARGO_TARGET_DIR/release/desktop-tool-display-probe" parity
    cargo build --offline --locked --release --features count
    "$CARGO_TARGET_DIR/release/desktop-tool-display-probe" "$arm" | tee -a alloc.tsv
    cargo build --offline --locked --release
    "$CARGO_TARGET_DIR/release/desktop-tool-display-probe" parity
    cp "$CARGO_TARGET_DIR/release/desktop-tool-display-probe" "$arm"
done
for ((i=0; i<8; i++)); do
    arms=(stock candidate)
    if ((i % 2)); then arms=(candidate stock); fi
    for arm in "${arms[@]}"; do "./$arm" "$arm" | tee -a runs.tsv; done
done
python3 - <<'PY'
from pathlib import Path
from collections import defaultdict
import statistics
times = defaultdict(lambda: defaultdict(list))
alloc = defaultdict(dict)
for raw in (Path("alloc.tsv").read_text()+Path("runs.tsv").read_text()).splitlines():
    tag, arm, name,*values=raw.split("\t")
    if tag=="time": times[name][arm].append(float(values[0]))
    else: alloc[name][arm]=tuple(map(int,values))
assert len(alloc)==len(times)==6
for name,data in alloc.items():
    a,b=(data[n] for n in ("stock","candidate"))
    assert b[1]<a[1], (name, a, b)
    x,y=(times[name][n] for n in ("stock","candidate"))
    assert len(x)==len(y)==8
    print(f"{name} allocs/requested bytes: {a} -> {b}; {statistics.median(x)/1000:.3f} -> {statistics.median(y)/1000:.3f} us")
PY
