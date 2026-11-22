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
: "${CARGO_HOME:?existing locked offline cache}"
: "${CARGO_TARGET_DIR:?existing warm Desktop target}"
: "${R122_RAW_CARGO_DIR:?existing raw output directory}"
[[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R122_RAW_CARGO_DIR ]]
exec 9< "$root/r67/m150-tools/build.lock"
flock -xn 9
if ps -eo comm | grep -xE 'cargo|rustc|pytest'; then
    echo 'HOLD another runtime seen' >&2
    exit 1
fi
export CARGO_INCREMENTAL=0 CARGO_NET_OFFLINE=true
free_on() { df -Pk "$1" | awk 'NR==2{print $4}'; }
tmp=${TMPDIR:-/tmp}
floor=524288
temp_floor=262144
growth=204800
initial_target=$(free_on "$CARGO_TARGET_DIR")
initial_tmp=$(free_on "$tmp")
fence() {
    local target_reserve=${1:-0} tmp_reserve=${2:-0} now_target now_tmp target_used tmp_used
    now_target=$(free_on "$CARGO_TARGET_DIR")
    now_tmp=$(free_on "$tmp")
    target_used=$((initial_target-now_target))
    tmp_used=$((initial_tmp-now_tmp))
    printf 'FENCE target_available_kib=%s temp_available_kib=%s target_growth_kib=%s temp_growth_kib=%s target_reserve_kib=%s temp_reserve_kib=%s\n' \
        "$now_target" "$now_tmp" "$target_used" "$tmp_used" "$target_reserve" "$tmp_reserve"
    ((now_target >= floor + target_reserve && now_tmp >= temp_floor + tmp_reserve &&
       target_used + target_reserve <= growth && tmp_used + tmp_reserve <= growth))
}
fence 32768 8192
printf '%s  %s\n' \
    25115b6fb01b930096807d6747e2ee7d71993488db8294413cc1cd4498e4fe95 "$seal" \
    2a71b35f8657bd48bc1b8d41fd2f8e9f7df4eeaceefe15c61daf7a810d8996fd "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
work=$(mktemp -d "$tmp/r122-desktop.XXXXXXXX")
printf '%s\n' "$work" > "$R122_RAW_CARGO_DIR/$mode-temp-root"
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
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities; existing R119 warm closure, no native deps")
PY
P=crates/tabs/src/layout.rs
T=src/ui/terminal/mod.rs
V=src/ui/terminal/view.rs
S=src/ui/"workspace"/spaces.rs
U=src/ui/chats/subagent.rs
scope=("$T" "$V" "$S" "$U" crates/tabs LICENSE-GPL)
mkdir pin after442
git -C "$repo" archive "$base" "${scope[@]}" | tar xf - -C pin
for f in "${scope[@]}"; do
    mkdir -p "after442/$(dirname "$f")"
    cp -a "$tree/$f" "after442/$f"
done
printf '%s  %s\n' \
    baa28f8c9f6929bb43218479a7f41edbb9f1255f765a12806886c1e069c8f5ad "pin/$P" \
    59c8651aeab8cebc2e01fb9fbd91957794617b81db0b23f4e21dc52bec4b8313 "after442/$P" \
    d654767717baf2f83184282ec19876b00617d7f560180f54a6d3008a21d10f40 "pin/$U" \
    0fe0018e0ec1acb3670eec3f78c44c14a256effb97a47c10e5750e06855446a3 "pin/$T" \
    e9ad0fa816577850aeb47bc29b30b540d7a9cb525366ac1c8f4d111ab5a238ac "pin/$V" | sha256sum -c --status
cmp "pin/$U" "after442/$U"
cmp "pin/$T" "after442/$T"
git -C after442 init -q
git -C after442 add .
before=$(du -sk pin after442 | awk '{s+=$1} END{print s}')
((before < 1024))
include=(--include="$T" --include="$V" --include="$S" --include="$U" --include='crates/tabs/*' --include=LICENSE-GPL)
while IFS= read -r patch; do
    git -C after442 apply --check "${include[@]}" "$patch"
    git -C after442 apply "${include[@]}" "$patch"
done < predecessors
git -C after442 diff --check
[[ $(git -C after442 diff --name-only) == "$(printf '%s\n' "$P" "$T" "$V")" ]]
git -C after442 add .
echo "PASS only exact requested projection staged: $before KiB initial stock/cumulative inputs (with cumulative index)"
for tier in pin after442; do
    if [[ $tier == pin ]]; then
        git -C "$tier" init -q
        git -C "$tier" add .
    fi
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
        diff -qr "$tier/crates/tabs" "$tier-$arm/crates/tabs"
        cmp "$tier/$T" "$tier-$arm/src/product_terminal.rs"
        cmp "$tier/$V" "$tier-$arm/src/product_view.rs"
        cmp "$tier/$S" "$tier-$arm/src/product_spaces.rs"
        cmp "$tier/$U" "$tier-$arm/src/product_subagent.rs"
    done
    changed=$(diff -qr "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ $(wc -l <<< "$changed") == 3 ]]
    for f in "$P" src/product_subagent.rs src/active.inc.rs; do
        grep -Fx "Files $tier-baseline/$f and $tier-candidate/$f differ" <<< "$changed" >/dev/null
    done
    echo "PASS $tier apply/reverse/rustfmt/whitespace; same exact terminal/current lifts, only active query changes"
done
for arm in baseline candidate; do
    cmp "pin-$arm/src/workspace.inc.rs" "after442-$arm/src/workspace.inc.rs"
    cmp "pin-$arm/src/active.inc.rs" "after442-$arm/src/active.inc.rs"
    ! cmp -s "pin-$arm/src/guard.rs" "after442-$arm/src/guard.rs"
done
fence 32768 8192
if [[ $mode == --prepare ]]; then echo 'PREPARED without compile or runtime.'; exit 0; fi
for tier in pin after442; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        raw="$R122_RAW_CARGO_DIR/$harness"
        (cd "$harness"
         export R122_ARM="$stamp"
         touch src/lib.rs crates/tabs/src/lib.rs
         python3 "$here/cargo_evidence.py" snapshot . "$raw"
         fence 32768 8192
         if ! cargo test -p desktop-document-visibility-probe -p proteus-tabs --lib --locked --offline -j1 --no-run --message-format=json > "$raw.cargo-json" 2> "$raw.cargo-stderr"; then
             cat "$raw.cargo-stderr"
             python3 -c 'import sys,json;print("\n".join(x["message"]["rendered"] for x in map(json.loads,open(sys.argv[1])) if x.get("reason")=="compiler-message"))' "$raw.cargo-json"
             exit 1
         fi
         fence
         python3 "$here/cargo_evidence.py" run . "$raw" "$stamp" "$here/source.patch"
         cat "$raw.work"
        )
    done
    cmp "$R122_RAW_CARGO_DIR/$tier-baseline.trace-full" "$R122_RAW_CARGO_DIR/$tier-candidate.trace-full"
done
cmp "$R122_RAW_CARGO_DIR/pin-candidate.trace-full" "$R122_RAW_CARGO_DIR/after442-candidate.trace-full"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo "PASS exact terminal current/visible, live and parked entity/Settings and ordered-active oracle parity; no app server/native/PTY used."
