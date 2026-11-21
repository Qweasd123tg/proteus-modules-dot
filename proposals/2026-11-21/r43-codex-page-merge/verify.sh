#!/usr/bin/env bash
# Focused source-only harness. Use dependency rlibs from a compatible Cargo build
# of the pinned Desktop (serde with derive, serde_json, uuid, proteus-contracts).
# The app modules and tabs themselves are always compiled from the specified Git object.
set -euo pipefail
if [[ $# != 5 ]]; then
    echo 'usage: bash verify.sh DESKTOP_REPO SERDE.rlib SERDE_JSON.rlib UUID.rlib PROTEUS_CONTRACTS.rlib' >&2
    exit 2
fi
here=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(realpath "$1"); shift
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
flags=(--edition=2024 -C debuginfo=0 -C strip=symbols)
for dep in serde serde_json uuid proteus_contracts; do
    file=$(realpath "$1"); shift
    flags+=(--extern "$dep=$file" -L "dependency=$(dirname -- "$file")")
done
if [[ $(uname -s) == Linux ]]; then flags+=(-C link-arg=-fuse-ld=lld); fi
cd "$scratch"
git init -q
git -C "$repo" archive "$base" src/conversations.rs src/ui/chats/codex.rs src/agents/codex/types.rs crates/tabs/src | tar xf -
git add src crates
git apply --check --index "$here/source.patch"
cp "$here/probe.rs" .
rustc --version
rustc "${flags[@]}" --crate-name=proteus_tabs --crate-type=rlib -C opt-level=2 crates/tabs/src/lib.rs -o libproteus_tabs.rlib
flags+=(--extern "proteus_tabs=$scratch/libproteus_tabs.rlib")
for arm in stock candidate; do
    if [[ $arm == candidate ]]; then
        git apply "$here/source.patch"
        git diff --check
        git apply --reverse --check "$here/source.patch"
    fi
    # Compile the page-merge statements verbatim with their production input types;
    # omit scheduling, cursor acceptance and other GPUI infrastructure.
    python3 - <<'PY'
from pathlib import Path
source = Path('src/ui/chats/codex.rs').read_text()
anchor = '.accept(cursor.as_deref(), page.next_cursor);'
assert source.count(anchor) == 1
block = source.split(anchor,1)[1].split('this.sessions_arrived',1)[0]
assert 'this.sessions' in block and 'this.deleting_sessions' in block
Path('page_merge.inc').write_text('{\n'+block+'\n}')
PY
    echo "=== $arm @ $base ==="
    rustc "${flags[@]}" --test probe.rs -o focused
    ./focused --test-threads=1
    rustc "${flags[@]}" -C opt-level=3 probe.rs -o "$arm"
done
for ((i=0; i<6; i++)); do
    arms=(stock candidate)
    if ((i % 2)); then arms=(candidate stock); fi
    for arm in "${arms[@]}"; do "./$arm" "$arm" | tee -a runs.tsv; done
done
python3 - <<'PY'
import csv, statistics
from collections import defaultdict
times = defaultdict(lambda: defaultdict(list))
orders = defaultdict(set)
for arm,name,n,p,digest,t in csv.reader(open("runs.tsv"), delimiter="\t"):
    k = (name,n,p)
    times[k][arm].append(int(t))
    orders[k].add(digest)
assert len(times)==10
print("scenario/rows/page: median microseconds, stock -> candidate")
for k, arms in times.items():
    assert len(orders[k])==1
    assert set(arms)=={"stock","candidate"} and all(len(a)==6 for a in arms.values())
    a,b=(statistics.median(arms[x])/1000 for x in ("stock","candidate"))
    print(f"{'/'.join(k)}: {a:.2f} -> {b:.2f}; {a/b:.2f}x; digest={next(iter(orders[k]))}")
PY
