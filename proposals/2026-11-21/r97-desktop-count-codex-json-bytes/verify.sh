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
    6cd32eaac3b68ac6b4f82703808e6ea94ba8752a1c2ac072b9e0b74d4aad8628 "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R97_BUILD_LOCK:?shared compiler lock}"
    : "${R97_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R97_RAW_CARGO_DIR ]]
    exec 9< "$R97_BUILD_LOCK"
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
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
R=src/agents/codex/router.rs
mkdir pin after419
git -C "$repo" archive "$base" src/agents/codex crates/codex-client LICENSE-APACHE | tar xf - -C pin
cp -a "$tree/." after419/
git -C after419 init -q
while IFS= read -r patch; do
    git -C after419 apply --check "$patch"
    git -C after419 apply "$patch"
done < predecessors
cmp "pin/$R" "after419/$R"
if cmp -s pin/crates/codex-client/src/process.rs after419/crates/codex-client/src/process.rs; then
    echo "missing cumulative transport difference"; exit 1
fi
for tier in pin after419; do
    git -C "$tier" init -q
    git -C "$tier" add "$R"
    git -C "$tier" apply --check --index "$here/source.patch"
    for arm in baseline candidate; do
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            [[ $(git -C "$tier" diff --name-only) == "$R" ]]
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$R"
        fi
        python3 "$here/materialize.py" "$tier" "$tier-$arm" "$here"
    done
    changed=$(diff -qr "$tier-baseline" "$tier-candidate" || test "$?" = 1)
    [[ "$changed" == "Files $tier-baseline/src/router.rs and $tier-candidate/src/router.rs differ" ]]
    echo "PASS $tier apply/reverse/rustfmt/whitespace: only Router file changed in exact harness"
done
cmp pin-candidate/src/router.rs after419-candidate/src/router.rs
if [[ $mode == --prepare ]]; then echo 'PREPARED without compile or runtime.'; exit 0; fi
for tier in pin after419; do
    for arm in baseline candidate; do
        for mode_name in compact ordered; do
            harness="$tier-$arm"
            stamp="$tier/$arm/$mode_name"
            raw="$R97_RAW_CARGO_DIR/$harness-$mode_name"
            (cd "$harness"
             export R97_ARM="$stamp"
             touch src/{lib,router}.rs crates/codex-client/src/lib.rs
             flags=()
             if [[ $mode_name == ordered ]]; then flags=(--features ordered); fi
             python3 "$here/cargo_evidence.py" snapshot . "$raw"
             fence
             if ! cargo test -p desktop-router-json-bytes-probe --lib --locked --offline -j1 --no-run --message-format=json "${flags[@]}" > "$raw.cargo-json" 2> "$raw.cargo-stderr"; then
                 cat "$raw.cargo-stderr"
                 python3 -c 'import sys,json;print("\n".join(x["message"]["rendered"] for x in map(json.loads,open(sys.argv[1])) if x.get("reason")=="compiler-message"))' "$raw.cargo-json"
                 exit 1
             fi
             fence
             python3 "$here/cargo_evidence.py" run . "$raw" "$stamp" "$here/source.patch"
             cat "$raw.trace" "$raw.work"
            )
        done
    done
    for mode_name in compact ordered; do
        cmp "$R97_RAW_CARGO_DIR/$tier-baseline-$mode_name.trace" "$R97_RAW_CARGO_DIR/$tier-candidate-$mode_name.trace"
    done
done
for mode_name in compact ordered; do
    cmp "$R97_RAW_CARGO_DIR/pin-candidate-$mode_name.trace" "$R97_RAW_CARGO_DIR/after419-candidate-$mode_name.trace"
done
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo "PASS exact count, routing and byte boundaries; no live service or native GUI launched."
