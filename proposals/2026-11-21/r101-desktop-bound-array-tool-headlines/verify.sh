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
    8cb9f60be50e517a12b1c13a4763f756881e1afbd88c81acf9d72e1648a98491 "$here/source.patch" \
    ab74609a6071fedc5bf6837a5c6b18d1481e153c08f095c3e05ab332c286eb7b "$here/cumulative.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R101_BUILD_LOCK:?shared compiler lock}"
    : "${R101_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R101_RAW_CARGO_DIR ]]
    exec 9< "$R101_BUILD_LOCK"
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
assert len(chosen)==14 and chosen <= identities("desktop.lock")
assert any(r[:2]==("serde_json","1.0.152") for r in chosen)
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
S=src/tool_display/mod.rs
mkdir pin after423
git -C "$repo" archive "$base" src/tool_display src/ui/chat/requests.rs | tar xf - -C pin
cp -a "$tree/." after423/
git -C after423 init -q
while IFS= read -r patch; do
    git -C after423 apply --check "$patch"
    git -C after423 apply "$patch"
done < predecessors
printf '%s  %s\n' \
    b1f4109d95af9e5f867323af4b974fdad9ec2b830a48d7f706005d751583b71d "pin/$S" \
    dc7b25512435d691e5b9fb3bbe031b48d5db6228e8e05cf3afbe5c21edaa8106 "after423/$S" | sha256sum -c --status
cmp pin/src/ui/chat/requests.rs after423/src/ui/chat/requests.rs
for tier in pin after423; do
    git -C "$tier" init -q
    git -C "$tier" add src/tool_display src/ui/chat/requests.rs
    patch="$here/source.patch"
    if [[ $tier == after423 ]]; then patch="$here/cumulative.patch"; fi
    git -C "$tier" apply --check --index --whitespace=error "$patch"
    for arm in baseline candidate; do
        harness="$tier-$arm"
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply --whitespace=error "$patch"
            git -C "$tier" apply --reverse --check "$patch"
            git -C "$tier" diff --check
            [[ $(git -C "$tier" diff --name-only) == "$S" ]]
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$S"
        fi
        python3 "$here/materialize.py" "$tier" "$harness" "$here"
    done
    change=$(diff -qr --no-dereference "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ "$change" == "Files $tier-baseline/src/tool_display/mod.rs and $tier-candidate/src/tool_display/mod.rs differ" ]]
    echo "PASS $tier apply/reverse/rustfmt/whitespace; inherited tests, patch parser, and exact approval display body unchanged"
done
python3 - <<'PY'
from pathlib import Path
def extract(file, start, end):
    s=Path(file).read_text()
    return s[s.index(start):s.index(end)]
s="src/tool_display/mod.rs"
for a,b in (("fn multi_subject<", "/// Several lines become one"), ("fn take_chars<", "fn arg_preview(")):
    assert extract("pin-candidate/"+s,a,b)==extract("after423-candidate/"+s,a,b)
print("PASS stock and cumulative variants share identical array renderer and scalar helper")
PY
if [[ $mode == --prepare ]]; then echo 'PREPARED without compile or runtime.'; exit 0; fi
for tier in pin after423; do
    patch="$here/source.patch"
    if [[ $tier == after423 ]]; then patch="$here/cumulative.patch"; fi
    for arm in baseline candidate; do
        harness="$tier-$arm"
        for features in sorted ordered; do
            stamp="$tier/$arm/$features"
            raw="$R101_RAW_CARGO_DIR/$harness-$features"
            (
                cd "$harness"
                export R101_ARRAY_ARM="$stamp"
                touch src/{lib,cases}.rs src/tool_display/mod.rs
                python3 "$here/cargo_evidence.py" snapshot . "$raw"
                flags=()
                if [[ $features == ordered ]]; then flags+=(--features preserve_order); fi
                fence
                if ! cargo test --lib --no-run --offline --locked -j1 --message-format=json "${flags[@]}" > "$raw.cargo-json" 2> "$raw.cargo-stderr"; then
                    cat "$raw.cargo-stderr"
                    python3 - "$raw.cargo-json" <<'PY'
import json,sys
for line in open(sys.argv[1]):
    record=json.loads(line)
    if record.get('reason')=='compiler-message':
        print(record['message'].get('rendered') or record['message'].get('message',''))
PY
                    exit 1
                fi
                fence
                python3 "$here/cargo_evidence.py" run . "$raw" "$stamp" "$patch"
                cat "$raw.trace" "$raw.work"
            )
        done
    done
done
for features in sorted ordered; do
    ref="$R101_RAW_CARGO_DIR/pin-baseline-$features.trace"
    for arm in pin-candidate after423-baseline after423-candidate; do
        cmp "$ref" "$R101_RAW_CARGO_DIR/$arm-$features.trace"
        cmp "${ref%.trace}.complete" "$R101_RAW_CARGO_DIR/$arm-$features.complete"
    done
done
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo 'PASS exact full formatting/display parity in both JSON modes; native UI and actions not run.'
