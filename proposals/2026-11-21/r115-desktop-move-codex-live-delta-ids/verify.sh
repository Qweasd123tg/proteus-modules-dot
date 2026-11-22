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
    f41d2517a7e951108a80e008b72538f6df37463a3c5dee56226353a054c51f59 "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R115_BUILD_LOCK:?shared compiler lock}"
    : "${R115_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R115_RAW_CARGO_DIR ]]
    exec 9< "$R115_BUILD_LOCK"
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
assert len(chosen) == 125
assert any(r[0] == "proteus-contracts" and r[2].endswith("#7cbc7206f03fac130d05bed2844de275476fedc8") for r in chosen)
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
P=src/transcript/external.rs
U=src/ui/chat/codex/mod.rs
mkdir pin after436
git -C "$repo" archive "$base" "$U" src/transcript src/agents/codex/{projection,types}.rs | tar xf - -C pin
cp -a "$tree/." after436/
git -C after436 init -q
while IFS= read -r patch; do
    git -C after436 apply --check "$patch"
    git -C after436 apply "$patch"
done < predecessors
printf '%s  %s\n' ffe3615886e84ef52bcd22ce1594151197d87a52a171be0d667d491e3e132c56 "pin/$P" | sha256sum -c --status
! cmp -s "pin/$P" "after436/$P"
! cmp -s "pin/$U" "after436/$U"
for tier in pin after436; do
    git -C "$tier" init -q
    git -C "$tier" add "$P" "$U"
    git -C "$tier" apply --check --index --whitespace=error "$here/source.patch"
    for arm in baseline candidate; do
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            [[ $(git -C "$tier" diff --name-only) == "$(printf '%s\n' "$P" "$U")" ]]
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$P" "$tier/$U"
        fi
        python3 "$here/materialize.py" "$tier" "$tier-$arm" "$here"
        diff -qr "$tier/src/transcript" "$tier-$arm/src/transcript"
        cmp "$tier/$U" "$tier-$arm/src/product_ui.rs"
        for f in projection.rs types.rs; do
            cmp "$tier/src/agents/codex/$f" "$tier-$arm/src/agents/codex/$f"
        done
    done
    changed=$(diff -qr "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ $(wc -l <<< "$changed") == 3 ]]
    for f in "$P" src/product_ui.rs src/lifted.rs; do
        grep -Fx "Files $tier-baseline/$f and $tier-candidate/$f differ" <<< "$changed" >/dev/null
    done
    echo "PASS $tier apply/reverse/rustfmt/whitespace: scoped transcript and UI hunks; exact source + lifted arms"
done
for arm in baseline candidate; do
    cmp "pin-$arm/src/lifted.rs" "after436-$arm/src/lifted.rs"
done
if [[ $mode == --prepare ]]; then echo 'PREPARED without compile or runtime.'; exit 0; fi
for tier in pin after436; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        raw="$R115_RAW_CARGO_DIR/$harness"
        (cd "$harness"
         export R115_ARM="$stamp"
         touch src/lib.rs
         python3 "$here/cargo_evidence.py" snapshot . "$raw"
         fence
         if ! cargo test -p desktop-codex-live-delta-ids-probe --lib --locked --offline -j1 --no-run --message-format=json > "$raw.cargo-json" 2> "$raw.cargo-stderr"; then
             cat "$raw.cargo-stderr"
             python3 -c 'import sys,json;print("\n".join(x["message"]["rendered"] for x in map(json.loads,open(sys.argv[1])) if x.get("reason")=="compiler-message"))' "$raw.cargo-json"
             exit 1
         fi
         fence
         python3 "$here/cargo_evidence.py" run . "$raw" "$stamp" "$here/source.patch"
         cat "$raw.work"
        )
    done
    cmp "$R115_RAW_CARGO_DIR/$tier-baseline.trace-full" "$R115_RAW_CARGO_DIR/$tier-candidate.trace-full"
done
cmp "$R115_RAW_CARGO_DIR/pin-candidate.trace-full" "$R115_RAW_CARGO_DIR/after436-candidate.trace-full"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo "PASS exact live delta dispatch/transcript byte parity; no app-server or native GUI launched."
