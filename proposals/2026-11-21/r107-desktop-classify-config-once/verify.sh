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
    237f0c1331fbf74c36051229ebcb9c87534ae51b584cfa9ee4fccec68327762a "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
core_tree="$root/r64/m150-source/core"
python3 "$here/seal_check.py" "$core_tree" "$seal" core
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R107_BUILD_LOCK:?shared compiler lock}"
    : "${R107_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R107_RAW_CARGO_DIR ]]
    exec 9< "$R107_BUILD_LOCK"
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
assert len(chosen)==38 and chosen <= identities("desktop.lock")
assert any(r[:2]==("toml","0.8.23") for r in chosen)
assert any(r[:2]==("serde_json","1.0.152") for r in chosen)
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
S=src/ui/launcher/config/catalog.rs
mkdir pin after429
git -C "$repo" archive "$base" src/ui/launcher/config scripts/portable/proteus-native | tar xf - -C pin
cp -a "$tree/." after429/
git -C after429 init -q
while IFS= read -r patch; do
    git -C after429 apply --check "$patch"
    git -C after429 apply "$patch"
done < predecessors
for file in "$S" src/ui/launcher/config/catalog/tests.rs src/ui/launcher/config/picker.rs scripts/portable/proteus-native; do
   cmp "pin/$file" "after429/$file"
done
for tier in pin after429; do
    git -C "$tier" init -q
    git -C "$tier" add "$S"
    git -C "$tier" apply --check --index --whitespace=error "$here/source.patch"
    cp "$tier/$S" "$tier.original.rs"
    for arm in baseline candidate; do
        harness="$tier-$arm"
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply --whitespace=error "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            [[ $(git -C "$tier" diff --name-only) == "$S" ]]
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$S"
            python3 - "$tier" <<'PY'
from pathlib import Path
import sys
tier=sys.argv[1]
old=Path(tier+".original.rs").read_text()
new=Path(tier+"/src/ui/launcher/config/catalog.rs").read_text()
changes="""        // Both branches classify the symlink target from the same lookup.
        let Ok(metadata) = path.metadata() else {
            continue;
        };
        let kind = metadata.file_type();
        if kind.is_dir() {"""
assert new==old.replace("        if path.is_dir() {",changes,1).replace("&& path.is_file() {","&& kind.is_file() {",1)
PY
        fi
        python3 "$here/materialize.py" "$tier" "$harness" "$here"
    done
    change=$(diff -qr --no-dereference "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ "$change" == "Files $tier-baseline/src/catalog.rs and $tier-candidate/src/catalog.rs differ" ]]
    echo "PASS $tier apply/reverse/rustfmt/whitespace; all canonicalization, label, UI, and cap source unchanged"
done
if [[ $mode == --prepare ]]; then echo 'PREPARED without compile or runtime.'; exit 0; fi
mkdir "$work/portable-setup"
cp -a "$core_tree/configs" "$work/portable-setup/configs"
diff -qr --no-dereference "$core_tree/configs" "$work/portable-setup/configs"
for tier in pin after429; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        raw="$R107_RAW_CARGO_DIR/$harness"
        (
            cd "$harness"
            export R107_CONFIG_ARM="$stamp"
            touch src/{lib,catalog,cases}.rs
            python3 "$here/cargo_evidence.py" snapshot . "$raw"
            fence
            if ! cargo test --lib --no-run --offline --locked -j1 --message-format=json > "$raw.cargo-json" 2> "$raw.cargo-stderr"; then
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
            python3 "$here/cargo_evidence.py" run . "$raw" "$stamp" "$here/source.patch" "$work/portable-setup"
            cat "$raw.work"
        )
    done
done
for arm in pin-candidate after429-baseline after429-candidate; do
    cmp "$R107_RAW_CARGO_DIR/pin-baseline.trace" "$R107_RAW_CARGO_DIR/$arm.trace"
done
python3 "$here/seal_check.py" "$tree" "$seal"
python3 "$here/seal_check.py" "$core_tree" "$seal" core
fence
echo 'PASS exact stable-tree results in the catalog and limits, one type lookup; no config or GUI launch.'
