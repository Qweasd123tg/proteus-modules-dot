#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 2 || ( "$1" != --prepare && "$1" != --run ) ]]; then
    echo "Usage: bash verify.sh [--prepare|--run] WORKSPACE_WITH_PINNED_INPUTS" >&2
    exit 2
fi
mode=$1
here=$(cd "$(dirname "$0")" && pwd)
root=$(realpath "$2")
repo="$root/r46/desktop/repo"
tree="$root/r64/m150-source/desktop"
seal="$root/r67/m150-tools/source-seal.json"
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
private="$root/r126/desktop/private"
if [[ $mode == --run ]]; then
    : "${R126_ADMIT:?requires separate sole runtime admission}"
    [[ $R126_ADMIT == sole-runtime-slot-confirmed ]]
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR ]]
    exec 9< "$root/r67/m150-tools/build.lock"
    flock -xn 9
    if ps -eo comm | grep -xE 'cargo|rustc|pytest|rust-lld|ld.lld'; then
        echo "HOLD competing runtime visible" >&2
        exit 1
    fi
    export CARGO_INCREMENTAL=0 CARGO_NET_OFFLINE=true
    free_on() { df -Pk "$1" | awk 'NR==2{print $4}'; }
    temp=${TMPDIR:-/tmp}
    initial_target=$(free_on "$CARGO_TARGET_DIR")
    initial_stage=$(free_on "$root")
    initial_temp=$(free_on "$temp")
    fence() {
        local held=${1:-0} temp_held=${2:-0} target stage tmp target_growth stage_growth temp_growth
        target=$(free_on "$CARGO_TARGET_DIR"); stage=$(free_on "$root"); tmp=$(free_on "$temp")
        target_growth=$((initial_target-target)); stage_growth=$((initial_stage-stage)); temp_growth=$((initial_temp-tmp))
        printf 'FENCE target_available_kib=%s stage_available_kib=%s temp_available_kib=%s target_growth_kib=%s stage_growth_kib=%s temp_growth_kib=%s reserve_kib=%s temp_reserve_kib=%s\n' \
            "$target" "$stage" "$tmp" "$target_growth" "$stage_growth" "$temp_growth" "$held" "$temp_held"
        ((target>=524288+held && stage>=524288+held && tmp>=262144+temp_held &&
          target_growth+held<=204800 && stage_growth+held<=204800 && temp_growth+temp_held<=204800))
    }
    fence 32768 8192
fi
printf '%s  %s\n' \
    25115b6fb01b930096807d6747e2ee7d71993488db8294413cc1cd4498e4fe95 "$seal" \
    0fbae273408cef0ff630f1ed4ab412f23d4073db1e9b44db75e1e77af4f4ba9f "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
mkdir -p "$private"
work=$(mktemp -d "$private/inputs.XXXXXXXX")
if [[ $mode == --run ]]; then
    raw=$(mkdir -p "$work/raw" && realpath "$work/raw")
    printf '%s\n' "$raw" > "$private/last-raw-dir"
fi
cd "$work"
python3 "$here/overlap.py" "$root" predecessors
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
cmp upstream.lock "$tree/Cargo.lock"
python3 - "$here/harness.lock" <<'PY'
from pathlib import Path
import sys, tomllib
def deps(path):
    rows=tomllib.loads(Path(path).read_text())["package"]
    return {(r["name"],r["version"],r["source"],r.get("checksum")) for r in rows if "source" in r}
locked=deps(sys.argv[1])
assert len(locked)==11 and locked<=deps("upstream.lock")
assert any(row[:2]==("serde_json","1.0.152") for row in locked)
print("PASS 11 locked Desktop dependency identities; existing R117 tabs closure, no UI/native dependencies")
PY

W=src/ui/"workspace"/windows.rs
E=src/ui/extensions/mod.rs
T=src/ui/tabs/mod.rs
P=crates/tabs/src/layout.rs
scope=("$W" "$E" "$T" crates/tabs LICENSE-GPL)
mkdir pin after444 original
git -C "$repo" archive "$base" "${scope[@]}" | tar xf - -C pin
for f in "${scope[@]}"; do
    mkdir -p "after444/$(dirname "$f")"
    cp -a "$tree/$f" "after444/$f"
done
for f in "$W" "$E" "$T"; do
    cmp "pin/$f" "after444/$f"
    mkdir -p "original/$(dirname "$f")"
    cp "pin/$f" "original/$f"
done
printf '%s  %s\n' \
    45f547f7c6c70ff3d67217f52aa2216c97557e880674d60aceb2626256abceff "pin/$W" \
    9ee6ee71d996c288f14763f2d9ce1fe4587351e7df4e15d1da556d8c49cb9600 "pin/$E" \
    2196538b9f80e77f1aa4ddb963625d8e77bebb5e1d78c402f3f5cf065fa5fda7 "pin/$T" \
    baa28f8c9f6929bb43218479a7f41edbb9f1255f765a12806886c1e069c8f5ad "pin/$P" \
    59c8651aeab8cebc2e01fb9fbd91957794617b81db0b23f4e21dc52bec4b8313 "after444/$P" | sha256sum -c --status
initial_staged=$(du -sk pin after444 original | awk '{s+=$1}END{print s}')
((initial_staged<1024))
git -C after444 init -q
git -C after444 add .
while IFS= read -r patch; do
    git -C after444 apply --check --whitespace=error --include='crates/tabs/*' "$patch"
    git -C after444 apply --whitespace=error --include='crates/tabs/*' "$patch"
done < predecessors
git -C after444 diff --check
[[ $(git -C after444 diff --name-only) == "$P" ]]
grep -q 'pub fn is_visible' "after444/$P"
git -C after444 add .
for tier in pin after444; do
    if [[ $tier == pin ]]; then
        git -C "$tier" init -q
        git -C "$tier" add .
    fi
    git -C "$tier" apply --check --index --whitespace=error "$here/source.patch"
    for arm in baseline candidate; do
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply --whitespace=error "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            [[ $(git -C "$tier" diff --name-only) == "$(printf '%s\n' "$E" "$T" "$W")" ]]
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$E" "$tier/$T" "$tier/$W"
        fi
        python3 "$here/materialize.py" "$tier" original "$tier-$arm" "$here"
        diff -qr "$tier/crates/tabs" "$tier-$arm/crates/tabs"
        cmp "$tier/$W" "$tier-$arm/src/product_windows.rs"
        cmp "$tier/$E" "$tier-$arm/src/product_extensions.rs"
        cmp "$tier/$T" "$tier-$arm/src/product_tabs.rs"
    done
    changed=$(diff -qr "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ $(wc -l <<< "$changed") == 6 ]]
    for f in src/{product_windows.rs,product_extensions.rs,product_tabs.rs,window.inc.rs,extensions.inc.rs,action.inc.rs}; do
        grep -Fx "Files $tier-baseline/$f and $tier-candidate/$f differ" <<< "$changed" >/dev/null
    done
    echo "PASS $tier exact apply/reverse/rustfmt and original group union oracle; only three production files and their lifts differ"
done
diff -qr pin-baseline/src after444-baseline/src
diff -qr pin-candidate/src after444-candidate/src
echo "PASS only $initial_staged KiB of initial Git/anchor inputs staged; no broader M200 reconstruction"
if [[ $mode == --prepare ]]; then
    echo "PREPARED: no compilation or executable scheduled."
    exit 0
fi
fence 32768 8192
for tier in pin after444; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        rerun="$raw/$harness"
        (cd "$harness"
         export R126_ARM="$stamp"
         touch src/lib.rs crates/tabs/src/lib.rs
         python3 "$here/cargo_evidence.py" snapshot . "$rerun"
         fence 32768 8192
         if ! cargo test -p desktop-terminal-suffix-probe -p proteus-tabs --lib --locked --offline -j1 --no-run --message-format=json > "$rerun.cargo-json" 2> "$rerun.cargo-stderr"; then
             cat "$rerun.cargo-stderr"
             python3 -c 'import sys,json;print("\n".join(x["message"]["rendered"] for x in map(json.loads,open(sys.argv[1])) if x.get("reason")=="compiler-message"))' "$rerun.cargo-json"
             exit 1
         fi
         fence
         python3 "$here/cargo_evidence.py" run . "$rerun" "$stamp" "$here/source.patch"
         cat "$rerun.work"
        )
    done
    cmp "$raw/$tier-baseline.trace-full" "$raw/$tier-candidate.trace-full"
done
cmp "$raw/pin-baseline.trace-full" "$raw/after444-baseline.trace-full"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo "PASS exact visible tab membership union, terminal document IDs and inert navigation order; no terminal, extension process, app server or native GUI launched"
