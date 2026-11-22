#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 2 || ( "$1" != --prepare && "$1" != --run ) ]]; then
    echo 'Usage: bash verify.sh [--prepare|--run] WORKSPACE_WITH_PINNED_INPUTS' >&2
    exit 2
fi
mode=$1
here=$(cd "$(dirname "$0")" && pwd)
root=$(realpath "$2")
repo="$root/r46/desktop/repo"
tree="$root/r64/m150-source/desktop"
seal="$root/r67/m150-tools/source-seal.json"
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
printf '%s  %s\n' \
    25115b6fb01b930096807d6747e2ee7d71993488db8294413cc1cd4498e4fe95 "$seal" \
    e7590d711a6934aa95f71a2d2bdc02a9266bfca330e34d744b6bddda2214a625 "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R113_BUILD_LOCK:?shared compiler lock}"
    : "${R113_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R113_RAW_CARGO_DIR ]]
    exec 9< "$R113_BUILD_LOCK"
    flock -xn 9
    if ps -eo comm | grep -xE 'cargo|rustc|pytest'; then
        echo 'HOLD another runtime seen' >&2
        exit 1
    fi
    export CARGO_INCREMENTAL=0 CARGO_NET_OFFLINE=true
    free_on() { df -Pk "$1" | awk 'NR==2{print $4}'; }
    floor=524288
    temp_floor=262144
    growth=204800
    initial_target=$(free_on "$CARGO_TARGET_DIR")
    initial_tmp=$(free_on "${TMPDIR:-/tmp}")
    fence() {
        local now_target now_tmp
        now_target=$(free_on "$CARGO_TARGET_DIR")
        now_tmp=$(free_on "${TMPDIR:-/tmp}")
        printf 'FENCE target_available_kib=%s temp_available_kib=%s target_growth_kib=%s temp_growth_kib=%s\n' "$now_target" "$now_tmp" "$((initial_target-now_target))" "$((initial_tmp-now_tmp))"
        ((now_target >= floor && now_tmp >= temp_floor && initial_target-now_target <= growth && initial_tmp-now_tmp <= growth))
    }
    fence
fi
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
cd "$work"
python3 "$here/overlap.py" "$root" predecessors
git -C "$repo" show "$base:Cargo.lock" > desktop.lock
cmp desktop.lock "$tree/Cargo.lock"
python3 - "$here/harness.lock" <<'PY'
from pathlib import Path
import sys,tomllib
def identities(path):
    data=tomllib.loads(Path(path).read_text())
    return {(r["name"],r["version"],r["source"],r.get("checksum")) for r in data["package"] if "source" in r}
chosen=identities(sys.argv[1])
assert chosen <= identities("desktop.lock")
assert any(r[:2]==("serde_json","1.0.152") for r in chosen)
assert len(chosen) == 22
assert any(r[:2] == ("async-channel", "2.5.0") for r in chosen)
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
P=src/ui/chat/codex/mod.rs
Y=src/ui/chat/stream_batch.rs
mkdir pin after434
git -C "$repo" archive "$base" "$P" "$Y" src/agents/codex/{router,projection,types}.rs crates/codex-client LICENSE-APACHE | tar xf - -C pin
cp -a "$tree/." after434/
git -C after434 init -q
while IFS= read -r patch; do
    git -C after434 apply --check "$patch"
    git -C after434 apply "$patch"
done < predecessors
printf '%s  %s\n' \
    0ca77028f6b47ae024eb76bc9e1fccb3968cf618e8ed8168a9ac36dbf26184e3 "pin/$P" \
    0ca77028f6b47ae024eb76bc9e1fccb3968cf618e8ed8168a9ac36dbf26184e3 "after434/$P" | sha256sum -c --status
for tier in pin after434; do
    git -C "$tier" init -q
    git -C "$tier" add "$P"
    git -C "$tier" apply --check --index --whitespace=error "$here/source.patch"
    for arm in baseline candidate; do
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            [[ $(git -C "$tier" diff --name-only) == "$P" ]]
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$P"
        fi
        python3 "$here/materialize.py" "$tier" "$tier-$arm" "$here"
        cmp "$tier/$P" "$tier-$arm/src/product_pump.rs"
        cmp "$tier/$Y" "$tier-$arm/src/product_stream_batch.rs"
        for f in router.rs projection.rs types.rs; do
            cmp "$tier/src/agents/codex/$f" "$tier-$arm/src/$f"
        done
    done
    changed=$(diff -qr "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ $(wc -l <<< "$changed") == 2 ]]
    for f in pump.rs product_pump.rs; do
        grep -Fx "Files $tier-baseline/src/$f and $tier-candidate/src/$f differ" <<< "$changed" >/dev/null
    done
    echo "PASS $tier apply/reverse/rustfmt/whitespace: only native pump and exact lifted body differ"
done
for arm in baseline candidate; do
    cmp "pin-$arm/src/pump.rs" "after434-$arm/src/pump.rs"
    cmp "pin-$arm/src/scheduler.rs" "after434-$arm/src/scheduler.rs"
done
if cmp -s pin-baseline/src/router.rs after434-baseline/src/router.rs; then
    echo "HOLD missing #421 accumulated Router change"
    exit 1
fi
if [[ $mode == --prepare ]]; then echo 'PREPARED without compile or runtime.'; exit 0; fi
for tier in pin after434; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        raw="$R113_RAW_CARGO_DIR/$harness"
        (cd "$harness"
         export R113_ARM="$stamp"
         touch src/lib.rs crates/codex-client/src/lib.rs
         python3 "$here/cargo_evidence.py" snapshot . "$raw"
         fence
         if ! cargo test -p desktop-codex-ui-batch-probe --lib --locked --offline -j1 --no-run --message-format=json > "$raw.cargo-json" 2> "$raw.cargo-stderr"; then
             cat "$raw.cargo-stderr"
             python3 -c 'import sys,json;print("\n".join(x["message"]["rendered"] for x in map(json.loads,open(sys.argv[1])) if x.get("reason")=="compiler-message"))' "$raw.cargo-json"
             exit 1
         fi
         fence
         python3 "$here/cargo_evidence.py" run . "$raw" "$stamp" "$here/source.patch"
         cat "$raw.work"
        )
    done
    cmp "$R113_RAW_CARGO_DIR/$tier-baseline.trace-full" "$R113_RAW_CARGO_DIR/$tier-candidate.trace-full"
done
cmp "$R113_RAW_CARGO_DIR/pin-candidate.trace-full" "$R113_RAW_CARGO_DIR/after434-candidate.trace-full"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo "PASS exact FIFO, batching, retry, rejection and disconnect parity; no app-server or native GUI launched."
