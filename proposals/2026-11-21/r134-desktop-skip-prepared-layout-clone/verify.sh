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
private="$root/r134/desktop/private"
if [[ $mode == --run ]]; then
    : "${R134_ADMIT:?requires separate sole runtime admission}"
    [[ $R134_ADMIT == sole-runtime-slot-confirmed ]]
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    [[ $(realpath "$CARGO_HOME") == "$root/r52/desktop/cargo" && -d $CARGO_HOME ]]
    [[ $(realpath "$CARGO_TARGET_DIR") == "$root/r52/desktop/target" && -d $CARGO_TARGET_DIR ]]
    [[ $(realpath "$(command -v cargo)") == "$root/r46/bootstrap/local/bin/cargo" ]]
    [[ $(realpath "$(command -v rustc)") == "$root/r46/bootstrap/local/bin/rustc" ]]
    printf '%s  %s\n' \
        841072d1d92f9e841d9ba5b0814182a0adf064acf4527cd120967b7bc49dcb66 "$(command -v cargo)" \
        bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6 "$(command -v rustc)" | sha256sum -c --status
    exec 9< "$root/r67/m150-tools/build.lock"
    flock -xn 9
    [[ ! -e "$root/r67/m150-tools/build.lock.r124-active-lease.json" ]]
    [[ ! -e "$root/r124/m200/active-lease.json" ]]
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
    87700fd236ca0a04086ae3f8a88e29c54166157c750feaf285cbd6abb7a9634e "$here/source.patch" | sha256sum -c --status
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
print("PASS 11 locked Desktop dependency identities; existing R117/R126/R128 tabs closure, no UI/native dependencies")
PY

W=src/ui/workspace.rs
S=src/ui/"workspace"/startup.rs
P=crates/tabs/src/pane.rs
L=crates/tabs/src/layout.rs
scope=("$W" "$S" crates/tabs LICENSE-GPL)
mkdir pin after449
git -C "$repo" archive "$base" "${scope[@]}" | tar xf - -C pin
for f in "${scope[@]}"; do
    mkdir -p "after449/$(dirname "$f")"
    cp -a "$tree/$f" "after449/$f"
done
cmp "pin/$W" "after449/$W"
cmp "pin/$S" "after449/$S"
printf '%s  %s\n' \
    8661b681ea8beb3706431dec300a9dbf17f3655bd62c0d7d19e4601bef23f16b "pin/$W" \
    84d220d7b6e5506b085a168cf9c23aa7a298be1164a079f28fa2a7ca0ef6e18c "pin/$S" | sha256sum -c --status
initial_staged=$(du -sk pin after449 | awk '{s+=$1}END{print s}')
((initial_staged<1024))
git -C after449 init -q
git -C after449 add .
while IFS= read -r patch; do
    git -C after449 apply --check --whitespace=error --include='crates/tabs/*' "$patch"
    git -C after449 apply --whitespace=error --include='crates/tabs/*' "$patch"
done < predecessors
git -C after449 diff --check
[[ $(git -C after449 diff --name-only) == "$(printf '%s\n' "$L" "$P")" ]]
grep -q 'pub fn is_visible' "after449/$L"
grep -q 'self.history.retain_mut' "after449/$P"
git -C after449 add .

for tier in pin after449; do
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
            [[ $(git -C "$tier" diff --name-only) == "$W" ]]
            "$root/r46/bootstrap/local/bin/rustfmt" --edition 2024 --config skip_children=true --check "$tier/$W"
        fi
        python3 "$here/materialize.py" "$tier" "$tier-$arm" "$here"
        diff -qr "$tier/crates/tabs" "$tier-$arm/crates/tabs"
        cmp "$tier/LICENSE-GPL" "$tier-$arm/LICENSE-GPL"
        cmp "$tier/$W" "$tier-$arm/src/product_workspace.rs"
        cmp "$tier/$S" "$tier-$arm/src/product_startup.rs"
    done
    changed=$(diff -qr "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ $changed == "$(for f in clone.inc.rs construct.inc.rs product_workspace.rs; do
        printf 'Files %s-baseline/src/%s and %s-candidate/src/%s differ\n' "$tier" "$f" "$tier" "$f"
    done)" ]]
    echo "PASS $tier exact apply/reverse/format check; real tabs source and exact lifted Workspace::new / Preparation::for_workspace"
done
for arm in baseline candidate; do
    diff -qr "pin-$arm/src" "after449-$arm/src"
    cmp "pin-$arm/Cargo.lock" "after449-$arm/Cargo.lock"
done
echo "PASS only $initial_staged KiB initial inputs staged; no broader milestone assembly"
if [[ $mode == --prepare ]]; then
    echo "PREPARED: no compilation or executable scheduled."
    exit 0
fi
fence 32768 8192
for tier in pin after449; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        rerun="$raw/$harness"
        (cd "$harness"
         export R134_ARM="$stamp"
         touch src/lib.rs crates/tabs/src/lib.rs
         python3 "$here/cargo_evidence.py" snapshot . "$rerun"
         fence 32768 8192
         if ! cargo test -p desktop-prepared-layout-probe -p proteus-tabs --lib --locked --offline -j1 --no-run --message-format=json > "$rerun.cargo-json" 2> "$rerun.cargo-stderr"; then
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
cmp "$raw/pin-baseline.trace-full" "$raw/after449-baseline.trace-full"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
python3 "$here/work_check.py" "$raw"
echo "PASS exact scripted scheduling and results; no real app startup/backend/native/UI/terminal/network execution"
