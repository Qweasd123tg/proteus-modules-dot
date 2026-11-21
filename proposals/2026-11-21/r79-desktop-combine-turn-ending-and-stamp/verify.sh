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
    31ce7c69b1ad9ee042d07422b17151365149966ef36cbe645a683343155860bd "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R79_BUILD_LOCK:?shared compiler lock}"
    : "${R79_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R79_RAW_CARGO_DIR ]]
    exec 9< "$R79_BUILD_LOCK"
    flock -xn 9
    if ps -eo comm | grep -xE 'cargo|rustc|pytest'; then
        echo 'HOLD another runtime seen' >&2
        exit 1
    fi
    export CARGO_INCREMENTAL=0 CARGO_NET_OFFLINE=true
    free_on() { df -Pk "$1" | awk 'NR==2{print $4}'; }
    floor=524288
    growth=204800
    initial_target=$(free_on "$CARGO_TARGET_DIR")
    initial_tmp=$(free_on "${TMPDIR:-/tmp}")
    fence() {
        local now_target now_tmp
        now_target=$(free_on "$CARGO_TARGET_DIR")
        now_tmp=$(free_on "${TMPDIR:-/tmp}")
        printf 'FENCE target_available_kib=%s temp_available_kib=%s target_growth_kib=%s temp_growth_kib=%s\n' "$now_target" "$now_tmp" "$((initial_target-now_target))" "$((initial_tmp-now_tmp))"
        ((now_target >= floor && now_tmp >= floor && initial_target-now_target <= growth && initial_tmp-now_tmp <= growth))
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
assert any(r[0]=="proteus-contracts" and r[2].endswith("#7cbc7206f03fac130d05bed2844de275476fedc8") for r in chosen)
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
chat=src/ui/chat
base_files=(src/transcript src/agents/codex/types.rs "$chat/stamp.rs" "$chat/thread.rs" "$chat/tool_chain.rs" "$chat/history.rs" "$chat/history/context.rs" "$chat/row_layout.rs" "$chat/scroller/scrollbar.rs" "$chat/session.rs")
others=(src/api/mod.rs src/declarative/session.rs "$chat/actions.rs" src/ui/extensions/declarative/{badge,view}.rs)
mkdir pin after401
git -C "$repo" archive "$base" "${base_files[@]}" | tar xf - -C pin
(cd "$tree"; tar cf - "${base_files[@]}" "${others[@]}") | tar xf - -C after401
while IFS= read -r patch; do
    git -C after401 apply --check "$patch"
    git -C after401 apply "$patch"
done < predecessors
cmp "pin/$chat/stamp.rs" "after401/$chat/stamp.rs"
for tier in pin after401; do
    git -C "$tier" init -q
    git -C "$tier" add src
    git -C "$tier" apply --check --index "$here/source.patch"
    for arm in baseline candidate; do
        harness="$tier-$arm"
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            rustfmt --edition 2024 --config skip_children=true --check "$tier/$chat/stamp.rs" "$tier/$chat/thread.rs"
        fi
        python3 "$here/materialize.py" "$tier" "$harness" "$here" > "$harness.contexts"
    done
    cmp "$tier-baseline.contexts" "$tier-candidate.contexts"
    echo "PASS $tier apply/reverse/whitespace/rustfmt, exact unchanged row/format/context slices"
done
cmp "pin-candidate/$chat/stamp.rs" "after401-candidate/$chat/stamp.rs"
cmp "pin-candidate/$chat/thread.inc.rs" "after401-candidate/$chat/thread.inc.rs"
echo 'PASS identical candidate stamp and row caller across tiers'
if [[ $mode == --prepare ]]; then
    echo 'PREPARED only. No runtime, timing, or native testing.'
    exit 0
fi
name=desktop-turn-end-probe
for tier in pin after401; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        fence
        (
            cd "$harness"
            export R79_TURN_END_PROBE_ARM="$stamp"
            touch src/main.rs src/ui/chat/stamp.rs src/ui/chat/thread.inc.rs
            status=0
            cargo build --offline --locked -j1 --message-format=json --bin "$name" > "$R79_RAW_CARGO_DIR/$harness.cargo-json" 2> "$R79_RAW_CARGO_DIR/$harness.cargo-stderr" || status=$?
            if (( status != 0 )); then
                cat "$R79_RAW_CARGO_DIR/$harness.cargo-stderr"
                python3 - "$R79_RAW_CARGO_DIR/$harness.cargo-json" <<'DIAG'
import json,sys
for line in open(sys.argv[1]):
    record=json.loads(line)
    if record.get('reason')=='compiler-message':
        print(record['message'].get('rendered') or record['message'].get('message',''))
DIAG
                exit "$status"
            fi
            fence
            python3 "$here/cargo_evidence.py" "$stamp" . "$R79_RAW_CARGO_DIR/$harness.cargo-json" "$R79_RAW_CARGO_DIR/$harness.trace" "$R79_RAW_CARGO_DIR/$harness.work" "$here/source.patch"
        )
        grep -Fx "ARM $stamp" "$R79_RAW_CARGO_DIR/$harness.work"
        cat "$R79_RAW_CARGO_DIR/$harness.trace"
        grep '^WORK ' "$R79_RAW_CARGO_DIR/$harness.work"
    done
    cmp "$R79_RAW_CARGO_DIR/$tier-baseline.trace" "$R79_RAW_CARGO_DIR/$tier-candidate.trace"
done
cmp "$R79_RAW_CARGO_DIR/pin-candidate.trace" "$R79_RAW_CARGO_DIR/after401-candidate.trace"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo 'PASS exact footer decisions, timestamp selection, copyability/draw gates and counted render path. No native GPUI.'
