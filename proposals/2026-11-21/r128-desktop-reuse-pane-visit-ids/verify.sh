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
private="$root/r128/desktop/private"
if [[ $mode == --run ]]; then
    : "${R128_ADMIT:?requires separate sole runtime admission}"
    [[ $R128_ADMIT == sole-runtime-slot-confirmed ]]
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
    ea4efcb183fa3425c1be5946bc789dfdb0c441b32bff1f105ee7c59008ace25a "$here/source.patch" | sha256sum -c --status
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
print("PASS 11 locked Desktop dependency identities; existing R117/R126 tabs closure, no UI/native dependencies")
PY

P=crates/tabs/src/pane.rs
L=crates/tabs/src/layout.rs
mkdir pin after447
git -C "$repo" archive "$base" crates/tabs LICENSE-GPL | tar xf - -C pin
mkdir -p after447/crates
cp -a "$tree/crates/tabs" after447/crates/tabs
cp -a "$tree/LICENSE-GPL" after447/LICENSE-GPL
printf '%s  %s\n' \
    00445bae4697eba2037703db6cb51ed4a0aa0027dfbbbd1bd9c6c99aacef6adf "pin/$P" \
    fd7ba895cd914bf006835f91ef78265383df4e84eea0b4329b4619779582ded8 "after447/$P" | sha256sum -c --status
initial_staged=$(du -sk pin after447 | awk '{s+=$1}END{print s}')
((initial_staged<1024))
git -C after447 init -q
git -C after447 add .
while IFS= read -r patch; do
    git -C after447 apply --check --whitespace=error --include='crates/tabs/*' "$patch"
    git -C after447 apply --whitespace=error --include='crates/tabs/*' "$patch"
done < predecessors
git -C after447 diff --check
[[ $(git -C after447 diff --name-only) == "$L" ]]
grep -q 'pub fn is_visible' "after447/$L"
git -C after447 add .
for tier in pin after447; do
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
            [[ $(git -C "$tier" diff --name-only) == "$P" ]]
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$P"
        fi
        python3 "$here/materialize.py" "$tier" "$tier-$arm" "$here"
        diff -qr "$tier/crates/tabs" "$tier-$arm/crates/tabs"
        cmp "$tier/LICENSE-GPL" "$tier-$arm/LICENSE-GPL"
    done
    changed=$(diff -qr "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ $changed == "Files $tier-baseline/$P and $tier-candidate/$P differ" ]]
    echo "PASS $tier exact apply/reverse/rustfmt and real tabs crate; only Pane::show changes"
done
for arm in baseline candidate; do
    diff -qr "pin-$arm/src" "after447-$arm/src"
    cmp "pin-$arm/Cargo.lock" "after447-$arm/Cargo.lock"
done
echo "PASS only $initial_staged KiB of initial Git/anchor inputs staged; no broader milestone reconstruction"
if [[ $mode == --prepare ]]; then
    echo "PREPARED: no compilation or executable scheduled."
    exit 0
fi
fence 32768 8192
for tier in pin after447; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        rerun="$raw/$harness"
        (cd "$harness"
         export R128_ARM="$stamp"
         touch src/lib.rs crates/tabs/src/lib.rs
         python3 "$here/cargo_evidence.py" snapshot . "$rerun"
         fence 32768 8192
         if ! cargo test -p desktop-pane-mru-probe -p proteus-tabs --lib --locked --offline -j1 --no-run --message-format=json > "$rerun.cargo-json" 2> "$rerun.cargo-stderr"; then
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
cmp "$raw/pin-baseline.trace-full" "$raw/after447-baseline.trace-full"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo "PASS exact history/MRU, active/close behavior and serialized pane/layout bytes; no native/UI/terminal/app-server execution"
