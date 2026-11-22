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
    3aacc076718b8f431911879ba5d6ac397e0c080c688e190d82dcfb2197baa8d1 "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R119_BUILD_LOCK:?shared compiler lock}"
    : "${R119_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R119_RAW_CARGO_DIR ]]
    exec 9< "$R119_BUILD_LOCK"
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
P=src/ui/terminal/mod.rs
V=src/ui/terminal/view.rs
S=src/ui/"workspace"/spaces.rs
U=src/ui/chats/subagent.rs
mkdir pin after440
git -C "$repo" archive "$base" "$P" "$V" "$S" "$U" crates/tabs LICENSE-GPL | tar xf - -C pin
cp -a "$tree/." after440/
git -C after440 init -q
while IFS= read -r patch; do
    git -C after440 apply --check "$patch"
    git -C after440 apply "$patch"
done < predecessors
printf '%s  %s\n' \
    0fe0018e0ec1acb3670eec3f78c44c14a256effb97a47c10e5750e06855446a3 "pin/$P" \
    e9ad0fa816577850aeb47bc29b30b540d7a9cb525366ac1c8f4d111ab5a238ac "pin/$V" | sha256sum -c --status
cmp "pin/$P" "after440/$P"
! cmp -s "pin/$V" "after440/$V"
for tier in pin after440; do
    git -C "$tier" init -q
    git -C "$tier" add "$P" "$V"
    git -C "$tier" apply --check --index --whitespace=error "$here/source.patch"
    for arm in baseline candidate; do
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            [[ $(git -C "$tier" diff --name-only) == "$(printf '%s\n' "$P" "$V")" ]]
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$P" "$tier/$V"
        fi
        python3 "$here/materialize.py" "$tier" "$tier-$arm" "$here"
        diff -qr "$tier/crates/tabs" "$tier-$arm/crates/tabs"
        cmp "$tier/$P" "$tier-$arm/src/product_terminal.rs"
        cmp "$tier/$V" "$tier-$arm/src/product_view.rs"
        cmp "$tier/$S" "$tier-$arm/src/product_spaces.rs"
        cmp "$tier/$U" "$tier-$arm/src/product_subagent.rs"
    done
    changed=$(diff -qr "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ $(wc -l <<< "$changed") == 4 ]]
    for f in guard.rs observed.rs product_terminal.rs product_view.rs; do
        grep -Fx "Files $tier-baseline/src/$f and $tier-candidate/src/$f differ" <<< "$changed" >/dev/null
    done
    echo "PASS $tier apply/reverse/rustfmt/whitespace: only memo sources and lifted derivatives differ"
done
for arm in baseline candidate; do
    cmp "pin-$arm/src/guard.rs" "after440-$arm/src/guard.rs"
    cmp "pin-$arm/src/workspace.inc.rs" "after440-$arm/src/workspace.inc.rs"
done
if [[ $mode == --prepare ]]; then echo 'PREPARED without compile or runtime.'; exit 0; fi
for tier in pin after440; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        raw="$R119_RAW_CARGO_DIR/$harness"
        (cd "$harness"
         export R119_ARM="$stamp"
         touch src/lib.rs crates/tabs/src/lib.rs
         python3 "$here/cargo_evidence.py" snapshot . "$raw"
         fence
         if ! cargo test -p desktop-terminal-lookup-key-probe --lib --locked --offline -j1 --no-run --message-format=json > "$raw.cargo-json" 2> "$raw.cargo-stderr"; then
             cat "$raw.cargo-stderr"
             python3 -c 'import sys,json;print("\n".join(x["message"]["rendered"] for x in map(json.loads,open(sys.argv[1])) if x.get("reason")=="compiler-message"))' "$raw.cargo-json"
             exit 1
         fi
         fence
         python3 "$here/cargo_evidence.py" run . "$raw" "$stamp" "$here/source.patch"
         cat "$raw.work"
        )
    done
    cmp "$R119_RAW_CARGO_DIR/$tier-baseline.trace-full" "$R119_RAW_CARGO_DIR/$tier-candidate.trace-full"
done
cmp "$R119_RAW_CARGO_DIR/pin-candidate.trace-full" "$R119_RAW_CARGO_DIR/after440-candidate.trace-full"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo "PASS exact real canonical bytes and lifted current/visible guard parity; no app-server or native GUI launched."
