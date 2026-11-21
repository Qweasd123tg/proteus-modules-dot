#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 5 || ( "$1" != --prepare && "$1" != --run ) ]]; then
    echo 'usage: bash verify.sh [--prepare|--run] PINNED_DESKTOP_CHECKOUT SEALED_M150_DESKTOP SOURCE_SEAL PATCH_393' >&2
    exit 2
fi
mode=$1
here=$(cd -- "$(dirname "$0")" && pwd)
repo=$(realpath "$2")
tree=$(realpath "$3")
seal=$(realpath "$4")
previous=$(realpath "$5")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
previous_sha=87c96e53a64f765f60599998ffb0e9d0374b56e60e5f1bfc1827259d458e32ea

if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?point to existing pinned offline Cargo cache}"
    : "${CARGO_TARGET_DIR:?point to existing warm Desktop focused target}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR ]]
    export CARGO_INCREMENTAL=0
    export CARGO_NET_OFFLINE=true
fi
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"
printf '%s  %s\n' "$previous_sha" "$previous" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
cmp upstream.lock "$tree/Cargo.lock"

p=src/ui/chat
files=(src/transcript src/agents/codex/types.rs "$p/history.rs" "$p/history/context.rs" "$p/history/tests.rs" "$p/row_layout.rs" "$p/stamp.rs" "$p/scroller/scrollbar.rs")
for variant in pin after-393; do
    mkdir "$variant"
    cd "$variant"
    mkdir preimage
    if [[ $variant == pin ]]; then
        git -C "$repo" archive "$base" "${files[@]}" | tar xf - -C preimage
        patch="$here/source.patch"
    else
        (cd "$tree"; tar cf - "${files[@]}") | tar xf - -C preimage
        git -C preimage apply --check "$previous"
        git -C preimage apply "$previous"
        patch="$here/cumulative.patch"
    fi
    git -C preimage init -q
    git -C preimage add src
    git -C preimage apply --index --check "$patch"
    for arm in baseline candidate; do
        cp -a preimage "$arm"
        if [[ $arm == candidate ]]; then
            git -C "$arm" apply "$patch"
            git -C "$arm" apply --reverse --check "$patch"
            git -C "$arm" diff --check
            rustfmt --edition 2024 --check "$arm/src/transcript/page_reuse_tests.rs"
            sed -n '/pub fn append_page(/,/pub fn remove(/p' "$arm/src/transcript/mod.rs" > append-page.txt
        fi
        python3 "$here/materialize.py" "$arm"
        cp "$here/harness.toml" "$arm/Cargo.toml"
        cp "$here/harness.lock" "$arm/Cargo.lock"
        cp "$here/probe.rs" "$arm/src/main.rs"
        cp "$here/ledger.rs" "$arm/src/ledger.rs"
        cp "$here/diagnostic.rs" "$arm/$p/history/diagnostic.rs"
    done
    # The same unit test should pass on each baseline: this production change
    # removes intermediate work rather than changing the final shared Arc.
    cp candidate/src/transcript/page_reuse_tests.rs baseline/src/transcript/
    python3 - baseline/src/transcript/mod.rs <<'OVERLAY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
src=path.read_text()
anchor='mod reasoning;\n#[cfg(test)]'
assert src.count(anchor)==1
path.write_text(src.replace(anchor,'#[cfg(test)]\nmod page_reuse_tests;\n'+anchor))
OVERLAY
    printf 'PASS %s exact projection/apply/reverse/diff checks\n' "$variant"
    cd "$w"
done
cmp pin/append-page.txt after-393/append-page.txt
echo 'PASS identical proposed append_page source on pin and after-393'
rustfmt --edition 2024 --config skip_children=true --check "$here/"{probe,ledger,diagnostic}.rs
python3 - <<'PY'
import tomllib
def ids(file):
    with open(file,'rb') as f:
        return {(r['name'],r['version'],r['source'],r.get('checksum')) for r in tomllib.load(f)['package'] if 'source' in r}
subset=ids('pin/baseline/Cargo.lock')
assert subset<=ids('upstream.lock')
assert any(p[0]=='proteus-contracts' and p[2].endswith('#7cbc7206f03fac130d05bed2844de275476fedc8') for p in subset)
print(f'PASS {len(subset)} pinned dependency identities including Desktop contracts')
PY
if [[ $mode == --prepare ]]; then
    echo 'PREPARED only: no tests, binaries or performance probe run.'
    exit 0
fi

rustc --version
name=desktop-history-byte-work-probe
for variant in pin after-393; do
    cd "$w/$variant"
    HISTORY_PROBE_EXPECT_SHARED_KEYSPACE=0
    if [[ $variant == after-393 ]]; then HISTORY_PROBE_EXPECT_SHARED_KEYSPACE=1; fi
    export HISTORY_PROBE_EXPECT_SHARED_KEYSPACE
    for arm in baseline candidate; do
        echo "=== $variant $arm exact scoped history/transcript tests ==="
        (
            cd "$arm"
            export R71_PROBE_ARM="$variant/$arm"
            touch src/transcript/mod.rs src/ui/chat/history/diagnostic.rs
            cargo test --offline --locked -j1 --bin "$name" 2>&1 | tee "../$arm.test-log"
            grep -q "Compiling $name" "../$arm.test-log"
            touch src/transcript/mod.rs src/ui/chat/history/diagnostic.rs
            cargo build --offline --locked -j1 --bin "$name" 2>&1 | tee "../$arm.build-log"
            grep -q "Compiling $name" "../$arm.build-log"
            "$CARGO_TARGET_DIR/debug/$name" > "../$arm.report"
        )
        grep -Fx "ARM $variant/$arm" "$arm.report"
        grep '^WORK ' "$arm.report"
        grep '^TRACE ' "$arm.report" > "$arm.trace"
    done
    cmp baseline.trace candidate.trace
    sha256sum candidate.trace
    python3 "$here/verify_counts.py" baseline.report candidate.report
done
cd "$w"
# #274 intentionally changed the stock seek counter; trace parity is
# required within each tier. The same conversion counts must hold in both.
for arm in baseline candidate; do
    grep '^WORK ' "pin/$arm.report" > "pin/$arm.work"
    grep '^WORK ' "after-393/$arm.report" > "after-393/$arm.work"
    cmp "pin/$arm.work" "after-393/$arm.work"
done
python3 "$here/seal_check.py" "$tree" "$seal"
echo 'PASS exact stock and cumulative traces; no native GUI, timing or RSS measured.'
