#!/usr/bin/env bash
# Use rlibs from an ABI-compatible build of the pinned Desktop dependencies.
set -eu -o pipefail
(( $# == 5 )) || { echo 'usage: verify.sh DESKTOP_REPO SERDE.rlib SERDE_JSON.rlib UUID.rlib PROTEUS_CONTRACTS.rlib' >&2; exit 2; }
packet=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$1"); shift
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
flags=(--edition=2024 -C debuginfo=0 -C strip=symbols)
for name in serde serde_json uuid proteus_contracts; do
  path=$(realpath "$1"); shift
  flags+=(--extern "$name=$path" -L dependency="$(dirname "$path")")
done
if [[ $(uname -s) == Linux ]]; then flags+=(-C link-arg=-fuse-ld=lld); fi
cd "$w"; git init -q
git -C "$repo" archive "$base" src/conversations.rs src/agents/codex/types.rs crates/tabs/src | tar xf -
git add src crates
git apply --index --check "$packet/source.patch"
cp "$packet/probe.rs" .
rustc --version
rustc "${flags[@]}" --crate-name=proteus_tabs --crate-type=rlib -C opt-level=2 crates/tabs/src/lib.rs -o libproteus_tabs.rlib
flags+=(--extern "proteus_tabs=$w/libproteus_tabs.rlib")
for arm in stock candidate; do
    if [[ $arm == candidate ]]; then
        git apply "$packet/source.patch"
        git diff --check
        git apply --reverse --check "$packet/source.patch"
        rustfmt --edition 2024 --check src/conversations.rs
    fi
    echo "=== $arm @$base ==="
    rustc "${flags[@]}" --test probe.rs -o tests
    ./tests --test-threads=1
    rustc "${flags[@]}" -Aunused_imports -C opt-level=3 --cfg count probe.rs -o counter
    ./counter "$arm" | tee -a alloc.tsv
    rustc "${flags[@]}" -C opt-level=3 probe.rs -o "$arm"
done
for ((i=0; i<6; i++)); do
    arms=(stock candidate); if ((i % 2)); then arms=(candidate stock); fi
    for arm in "${arms[@]}"; do "./$arm" "$arm" | tee -a runs.tsv; done
done
python3 - <<'PY'
import csv, statistics
from collections import defaultdict
times=defaultdict(lambda:defaultdict(list))
alloc=defaultdict(dict)
hashes=defaultdict(set)
for _,a,k,n,h,t in csv.reader(open("runs.tsv"),delimiter="\t"):
    times[k,n][a].append(int(t)); hashes[k,n].add(h)
for _,a,k,n,h,c,b in csv.reader(open("alloc.tsv"),delimiter="\t"):
    alloc[k,n][a]=int(c),int(b); hashes[k,n].add(h)
assert len(times)==len(hashes)==8
assert alloc["empty","0"] == {"stock":(0,0), "candidate":(0,0)}
for k, pair in alloc.items():
    if k == ("empty","0"): continue
    assert pair["candidate"][0] < pair["stock"][0] and pair["candidate"][1] < pair["stock"][1], (k,pair)
assert alloc["roots","4096"]["candidate"][0] == 1
for k,arms in times.items():
    assert all(len(v)==6 for v in arms.values()) and set(arms)=={"stock","candidate"} and len(hashes[k])==1
    a,b=(statistics.median(arms[arm])/1000 for arm in ("stock","candidate"))
    print(f"{'/'.join(k)} us: {a:.2f} -> {b:.2f}; allocations, requested bytes: {alloc[k]['stock']} -> {alloc[k]['candidate']}")
PY
