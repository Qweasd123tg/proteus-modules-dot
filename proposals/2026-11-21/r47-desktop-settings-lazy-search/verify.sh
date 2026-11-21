#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 )) || { echo 'usage: bash verify.sh PROTEUS_DESKTOP_CHECKOUT' >&2; exit 2; }
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; git init -q
git -C "$repo" archive "$base" src/ui/settings/{search,spot,client}.rs src/settings/catalog.rs src/preferences.rs | tar xf -
git add src
git apply --index --check "$here/source.patch"
cp "$here/probe.rs" .
rustc --version
for arm in stock candidate; do
    if [[ $arm == candidate ]]; then
        git apply "$here/source.patch"
        git apply --reverse --check "$here/source.patch"
        git diff --check
        rustfmt --edition 2024 --check src/ui/settings/search.rs
    fi
    echo "=== $arm @$base ==="
    python3 "$here/extract.py"
    rustc --edition=2024 --test probe.rs -o tests
    ./tests --test-threads=1
    rustc --edition=2024 -O -Aunused_imports --cfg count probe.rs -o counter
    ./counter "$arm" | tee -a alloc.tsv
    rustc --edition=2024 -O probe.rs -o "$arm"
done
for ((i=0; i<8; i++)); do
    arms=(stock candidate)
    if ((i % 2)); then arms=(candidate stock); fi
    for arm in "${arms[@]}"; do
        ./"$arm" "$arm" | tee -a runs.tsv
    done
done
python3 - <<'PY'
from pathlib import Path
from collections import defaultdict
import statistics
times = defaultdict(lambda: defaultdict(list))
alloc = defaultdict(dict)
digest = defaultdict(set)
for raw in (Path("alloc.tsv").read_text()+Path("runs.tsv").read_text()).splitlines():
    tag, arm, *fields=raw.split("\t")
    if tag=="parity":
        digest[tag].add(fields[0]); continue
    name,h,*values=fields
    digest[name].add(h)
    if tag=="time": times[name][arm].append(int(values[0]))
    else: alloc[name][arm]=tuple(map(int,values))
assert len(alloc)==7 and len(times)==6 and len(digest)==8
assert all(len(x)==1 for x in digest.values())
print("PASS identical outputs, incl. 66 generated query/catalog pairs")
for name,data in alloc.items():
    a,b=(data[n] for n in ("stock","candidate"))
    if name in ("real-empty", "stress-miss"): assert a==b
    else: assert b[0]<a[0] and b[1]<a[1]
    text=f"{name} allocations and requested bytes: {a} -> {b}"
    if name in times:
        a,b=(times[name][n] for n in ("stock","candidate"))
        assert len(a)==len(b)==8
        text+=f"; {statistics.median(a)/1000:.2f} -> {statistics.median(b)/1000:.2f} us"
    print(text)
PY
