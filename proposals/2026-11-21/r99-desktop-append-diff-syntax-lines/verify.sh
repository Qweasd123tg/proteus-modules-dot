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
    fd2ddf8ef407afd1e3a8b36492f8e369e5a8de30c2ccb30574053f1ad6815bef "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R99_BUILD_LOCK:?shared compiler lock}"
    : "${R99_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R99_RAW_CARGO_DIR ]]
    exec 9< "$R99_BUILD_LOCK"
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
assert len(chosen)==7 and chosen <= identities("desktop.lock")
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
S=src/ui/diff/syntax.rs
mkdir pin after421
git -C "$repo" archive "$base" src/ui/diff crates/diff LICENSE-GPL | tar xf - -C pin
cp -a "$tree/." after421/
git -C after421 init -q
while IFS= read -r patch; do
    git -C after421 apply --check "$patch"
    git -C after421 apply "$patch"
done < predecessors
cmp "pin/$S" "after421/$S"
if cmp -s pin/crates/diff/src/parse.rs after421/crates/diff/src/parse.rs || cmp -s pin/src/ui/diff/mod.rs after421/src/ui/diff/mod.rs; then
    echo 'Missing inherited parser or whole-diff difference'; exit 1
fi
for tier in pin after421; do
    git -C "$tier" init -q
    git -C "$tier" add src/ui/diff crates/diff
    git -C "$tier" apply --check --index --whitespace=error "$here/source.patch"
    for arm in baseline candidate; do
        harness="$tier-$arm"
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply --whitespace=error "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            [[ $(git -C "$tier" diff --name-only) == "$S" ]]
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$S"
        fi
        python3 "$here/materialize.py" "$tier" "$harness" "$here"
    done
    change=$(diff -qr --no-dereference "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ "$change" == "Files $tier-baseline/src/syntax.rs and $tier-candidate/src/syntax.rs differ" ]]
    echo "PASS $tier apply/reverse/rustfmt/whitespace: only the syntax input changes, not the tier parser or the renderer"
done
cmp pin-candidate/src/syntax.rs after421-candidate/src/syntax.rs
if [[ $mode == --prepare ]]; then echo 'PREPARED without compile or runtime.'; exit 0; fi
name=desktop-diff-syntax-probe
compile() {
    local prefix=$1
    shift
    if ! cargo "$@" --offline --locked -j1 --message-format=json > "$prefix.cargo-json" 2> "$prefix.cargo-stderr"; then
        cat "$prefix.cargo-stderr"
        python3 - "$prefix.cargo-json" <<'PY'
import json,sys
for line in open(sys.argv[1]):
    record=json.loads(line)
    if record.get('reason')=='compiler-message':
        print(record['message'].get('rendered') or record['message'].get('message',''))
PY
        exit 1
    fi
}
for tier in pin after421; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        raw="$R99_RAW_CARGO_DIR/$harness"
        (
            cd "$harness"
            export R99_DIFF_ARM="$stamp"
            touch src/{main,syntax}.rs crates/diff/src/{lib,parse,tests}.rs
            python3 "$here/artifact.py" snapshot . > "$raw.inputs"
            fence
            compile "$raw.unit" test --no-run -p proteus-diff --lib
            fence
            python3 "$here/artifact.py" unit "$stamp" . "$raw.unit" "$here/source.patch" > "$raw.unit.artifact"
            grep '^test result: ok\.' "$raw.unit.stdout" | sed -E 's/; finished in.*$//'
            compile "$raw.probe" build --bin "$name"
            fence
            python3 "$here/artifact.py" probe "$stamp" . "$raw.probe" "$here/source.patch" > "$raw.probe.artifact"
            cat "$raw.probe.stdout" "$raw.probe.stderr"
        )
    done
    cmp "$R99_RAW_CARGO_DIR/$tier-baseline.probe.stdout" "$R99_RAW_CARGO_DIR/$tier-candidate.probe.stdout"
done
cmp "$R99_RAW_CARGO_DIR/pin-candidate.probe.stdout" "$R99_RAW_CARGO_DIR/after421-candidate.probe.stdout"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo 'PASS exact syntax input/ranges/modeled output, local parser tests; no native GPUI.'
