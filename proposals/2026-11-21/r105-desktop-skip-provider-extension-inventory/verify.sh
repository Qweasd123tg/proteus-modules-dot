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
    50b71043105132633b0168ef1808ab278d393b446af4b04e36b366c1e06741eb "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
extension_tree="$root/r64/m150-source/extensions"
python3 "$here/seal_check.py" "$extension_tree" "$seal" extensions
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R105_BUILD_LOCK:?shared compiler lock}"
    : "${R105_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R105_RAW_CARGO_DIR ]]
    exec 9< "$R105_BUILD_LOCK"
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
assert len(chosen)==132 and chosen <= identities("desktop.lock")
assert any(r[0]=="proteus-contracts" and r[2].endswith("#7cbc7206f03fac130d05bed2844de275476fedc8") for r in chosen)
assert any(r[:2]==("sha2","0.10.9") for r in chosen)
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
C=src/catalog/connections.rs
I=src/catalog/inventory.rs
mkdir pin after427
git -C "$repo" archive "$base" src/declarative src/catalog src/backend.rs src/preferences.rs src/main.rs src/ui/settings/provider_auth.rs src/ui/settings/provider_creation.rs | tar xf - -C pin
cp -a "$tree/." after427/
git -C after427 init -q
while IFS= read -r patch; do
    git -C after427 apply --check "$patch"
    git -C after427 apply "$patch"
done < predecessors
cmp "pin/$C" "after427/$C"
if cmp -s "pin/$I" "after427/$I"; then
    echo 'HOLD missing #427 cumulative inventory behavior'; exit 1
fi
for file in src/ui/settings/provider_auth.rs src/ui/settings/provider_creation.rs; do
    cmp "pin/$file" "after427/$file"
done
for tier in pin after427; do
    git -C "$tier" init -q
    git -C "$tier" add "$C" "$I"
    git -C "$tier" apply --check --index --whitespace=error "$here/source.patch"
    cp "$tier/$C" "$tier.connections.before"
    cp "$tier/$I" "$tier.inventory.before"
    for arm in baseline candidate; do
        harness="$tier-$arm"
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply --whitespace=error "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            [[ $(git -C "$tier" diff --name-only) == "$C"$'\n'"$I" ]]
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$C" "$tier/$I"
            python3 - "$tier" <<'PY'
from pathlib import Path
import sys
tier=sys.argv[1]
c=Path(tier+".connections.before").read_text()
i=Path(tier+".inventory.before").read_text()
assert Path(tier+"/src/catalog/connections.rs").read_text()==c.replace("discover_with_inventory(installed, Inventory::local())","discover_with_inventory(installed, Inventory::local_modules())",1)
new=Path(tier+"/src/catalog/inventory.rs").read_text()
a=new.index("    /// Provider choices only consume")
b=new.index("    pub fn local() -> Self",a)
assert new[:a]+new[b:]==i
assert "resolve_binary(&crate::backend::proteus_binary())" in new[a:b]
assert "inventory.read_modules(&backend);" in new[a:b]
assert "extension" not in new[a:b].split("pub(super) fn local_modules")[1]
PY
        fi
        python3 "$here/materialize.py" "$tier" "$harness" "$here" "$extension_tree/packages"
    done
    change=$(diff -qr --no-dereference "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ "$change" == "Files $tier-baseline/$C and $tier-candidate/$C differ"$'\n'"Files $tier-baseline/$I and $tier-candidate/$I differ" ]]
    echo "PASS $tier apply/reverse/rustfmt/whitespace; full catalog/module/hash/receipt/auth source paths unchanged"
done
if [[ $mode == --prepare ]]; then echo 'PREPARED without compile or runtime.'; exit 0; fi
python3 "$here/fixture.py" "$work/provider-fixture"
for tier in pin after427; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        raw="$R105_RAW_CARGO_DIR/$harness"
        (
            cd "$harness"
            export R105_PROVIDER_ARM="$stamp"
            touch src/lib.rs src/catalog/{inventory,connections}.rs
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
            python3 "$here/cargo_evidence.py" run . "$raw" "$stamp" "$here/source.patch" "$extension_tree/packages" "$work/provider-fixture"
            cat "$raw.trace" "$raw.work"
        )
    done
done
for arm in pin-candidate after427-baseline after427-candidate; do
    cmp "$R105_RAW_CARGO_DIR/pin-baseline.trace" "$R105_RAW_CARGO_DIR/$arm.trace"
done
python3 "$here/seal_check.py" "$tree" "$seal"
python3 "$here/seal_check.py" "$extension_tree" "$seal" extensions
fence
echo 'PASS exact provider and full catalog parity; no provider command, auth, external network or GUI run.'
