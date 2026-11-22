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
private="$root/r136/desktop/private"
if [[ $mode == --run ]]; then
    : "${R136_ADMIT:?requires separate sole runtime admission}"
    [[ $R136_ADMIT == sole-runtime-slot-confirmed ]]
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
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
    04c23b711e2ab52da2a13f420689d68196928c90ed7e7d0d7656857622634a79 "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
mkdir -p "$private"
work=$(mktemp -d "$private/inputs.XXXXXXXX")
if [[ $mode == --run ]]; then
    raw=$(mkdir -p "$work/raw" && realpath "$work/raw")
    printf '%s\n' "$raw" > "$private/last-raw-dir"
fi
cd "$work"
python3 "$here/overlap.py" "$root" predecessors "$here/scope.txt"
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
cmp upstream.lock "$tree/Cargo.lock"
python3 "$here/cache_plan.py" check "$root" "$here/harness.lock"
coregit="$root/r52/desktop/cargo/git/checkouts/proteus-core-7355afd4bdf4a66a/7cbc720"
git -C "$coregit" show 7cbc7206f03fac130d05bed2844de275476fedc8:crates/proteus-contracts/src/app_protocol/settings.rs > settings.rs
printf '%s  %s\n' 89f3df39935e29e361b37f7214f2afcf0d6d58fcb9429eb1202870eac186feba settings.rs | sha256sum -c --status
mapfile -t scope < "$here/scope.txt"
mkdir pin after451
git -C "$repo" archive "$base" "${scope[@]}" | tar xf - -C pin
for f in "${scope[@]}"; do
    mkdir -p "after451/$(dirname "$f")"
    cp -a "$tree/$f" "after451/$f"
done
initial_staged=$(du -sk pin after451 | awk '{s+=$1}END{print s}')
((initial_staged<2048))
git -C after451 init -q
git -C after451 add .
args=()
for f in "${scope[@]}"; do
    if [[ -d pin/$f ]]; then args+=("--include=$f/*"); else args+=("--include=$f"); fi
done
while IFS= read -r patch; do
    git -C after451 apply --check --whitespace=error "${args[@]}" "$patch"
    git -C after451 apply --whitespace=error "${args[@]}" "$patch"
done < predecessors
git -C after451 diff --check
grep -q 'rows_from' after451/src/declarative/widget.rs || grep -q 'Arc<Vec<super::tree::Row>>' after451/src/declarative/widget.rs
git -C after451 add .
W=src/declarative/widget.rs
I=src/ui/extensions/declarative/images.rs
for tier in pin after451; do
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
            [[ $(git -C "$tier" diff --name-only) == "$(printf '%s\n' "$W" "$I")" ]]
            "$root/r46/bootstrap/local/bin/rustfmt" --edition 2024 --config skip_children=true --check "$tier/$W" "$tier/$I"
        fi
        python3 "$here/materialize.py" "$tier" "$tier-$arm" "$here" settings.rs > "$tier-$arm.safety"
        cmp "$tier/$W" "$tier-$arm/src/declarative/widget.rs"
        diff -qr --no-dereference "$tier/crates/diff" "$tier-$arm/crates/diff"
    done
    cmp "$tier-baseline.safety" "$tier-candidate.safety"
    changed=$(diff -qr "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ $changed == "$(printf 'Files %s-baseline/%s and %s-candidate/%s differ\n' "$tier" "product/$W" "$tier" "product/$W" "$tier" "product/$I" "$tier" "product/$I" "$tier" src/declarative/widget.rs "$tier" src/declarative/widget.rs "$tier" src/images/mode.inc.rs "$tier" src/images/mode.inc.rs "$tier" src/images.rs "$tier" src/images.rs)" ]]
    echo "PASS $tier apply/reverse/exact safety sections and exact real XML/declarative/diff sources"
done
cmp <(grep -v 'native-retained-view$' pin-baseline.safety) <(grep -v 'native-retained-view$' after451-baseline.safety)
for arm in baseline candidate; do
    cmp "pin-$arm/Cargo.lock" "after451-$arm/Cargo.lock"
done
echo "PASS only $initial_staged KiB initial source staging; no broader milestone or registry copied"
if [[ $mode == --prepare ]]; then
    echo "PREPARED: no compilation or executable scheduled."
    exit 0
fi
fence 32768 8192
export CARGO_HOME="$work/cargo-exact"
python3 "$here/cache_plan.py" stage "$root" "$here/harness.lock" "$CARGO_HOME"
fence 32768 8192
for tier in pin after451; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        rerun="$raw/$harness"
        (cd "$harness"
         export R136_ARM="$stamp"
         touch src/lib.rs crates/diff/src/lib.rs
         python3 "$here/cargo_evidence.py" snapshot . "$rerun"
         fence 32768 8192
         if ! cargo test -p desktop-svg-source-probe --lib --locked --offline -j1 --no-run --message-format=json > "$rerun.cargo-json" 2> "$rerun.cargo-stderr"; then
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
cmp "$raw/pin-baseline.trace-full" "$raw/after451-baseline.trace-full"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
python3 "$here/work_check.py" "$raw"
echo "PASS real typed/validation/cache/svg budget; no native rendering/network/extension/process executed"
