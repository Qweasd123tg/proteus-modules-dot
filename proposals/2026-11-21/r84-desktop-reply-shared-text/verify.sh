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
ext="$root/r64/m150-source/extensions"
seal="$root/r67/m150-tools/source-seal.json"
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
printf '%s  %s\n' \
    25115b6fb01b930096807d6747e2ee7d71993488db8294413cc1cd4498e4fe95 "$seal" \
    5cb36e1c8af665d2fc729a2631ba82b0bfebb308609eda17fd3ed98e4ce275d6 "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R84_BUILD_LOCK:?shared compiler lock}"
    : "${R84_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R84_RAW_CARGO_DIR ]]
    exec 9< "$R84_BUILD_LOCK"
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
python3 "$here/bundled_inputs.py" "$ext" "$seal"
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
changed=("$chat/replies.rs" src/declarative/protocol.rs src/ui/extensions/declarative/{content.rs,content/tests.rs,runtime.rs,runtime/content_queue.rs})
base_files=("${changed[@]}" src/declarative/{manifest,icons,session}.rs src/declarative/{process.rs,process/io.rs} src/preferences.rs src/ui/extensions/{mod.rs,declarative/mod.rs} src/ui/extensions/declarative/inline_content.rs src/transcript src/agents/codex/types.rs)
others=(src/api/mod.rs src/ui/chats.rs src/ui/chat/{history,stamp,thread,actions,session}.rs src/ui/extensions/declarative/{badge,view}.rs)
mkdir pin after407
git -C "$repo" archive "$base" "${base_files[@]}" | tar xf - -C pin
(cd "$tree"; tar cf - "${base_files[@]}" "${others[@]}") | tar xf - -C after407
while IFS= read -r patch; do
    git -C after407 apply --check "$patch"
    git -C after407 apply "$patch"
done < predecessors
echo "PASS both exact predecessor stacks admitted; #405 has distinct registry hunks"
for tier in pin after407; do
    git -C "$tier" init -q
    git -C "$tier" add src
    git -C "$tier" apply --check --index "$here/source.patch"
    for arm in baseline candidate; do
        harness="$tier-$arm"
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            for path in "${changed[@]}"; do rustfmt --edition 2024 --config skip_children=true --check "$tier/$path"; done
        fi
        python3 "$here/materialize.py" "$tier" "$harness" "$ext" "$here" > "$harness.contexts"
    done
    cmp "$tier-baseline.contexts" "$tier-candidate.contexts"
    echo "PASS $tier apply/reverse/whitespace/rustfmt, exact unchanged queue/admission, render and wire source neighborhoods"
done
cmp pin-candidate/src/declarative/protocol.rs after407-candidate/src/declarative/protocol.rs
cmp pin-candidate/src/ui/extensions/declarative/runtime.inc.rs after407-candidate/src/ui/extensions/declarative/runtime.inc.rs
cmp pin-baseline.contexts after407-baseline.contexts
echo 'PASS identical candidate framing/render methods and unchanged contexts across tiers'
if [[ $mode == --prepare ]]; then
    echo 'PREPARED only. No runtime, timing, or native testing.'
    exit 0
fi
name=desktop-reply-source-probe
for tier in pin after407; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        fence
        (
            cd "$harness"
            export R84_REPLY_SOURCE_PROBE_ARM="$stamp"
            touch src/main.rs src/ui/chat/replies.rs src/ui/extensions/declarative/content.rs
            status=0
            cargo build --offline --locked -j1 --message-format=json --bin "$name" > "$R84_RAW_CARGO_DIR/$harness.cargo-json" 2> "$R84_RAW_CARGO_DIR/$harness.cargo-stderr" || status=$?
            if (( status != 0 )); then
                cat "$R84_RAW_CARGO_DIR/$harness.cargo-stderr"
                python3 - "$R84_RAW_CARGO_DIR/$harness.cargo-json" <<'DIAG'
import json,sys
for line in open(sys.argv[1]):
    record=json.loads(line)
    if record.get('reason')=='compiler-message':
        print(record['message'].get('rendered') or record['message'].get('message',''))
DIAG
                exit "$status"
            fi
            fence
            python3 "$here/cargo_evidence.py" "$stamp" . "$R84_RAW_CARGO_DIR/$harness.cargo-json" "$R84_RAW_CARGO_DIR/$harness.trace" "$R84_RAW_CARGO_DIR/$harness.work" "$here/source.patch"
        )
        grep -Fx "ARM $stamp" "$R84_RAW_CARGO_DIR/$harness.work"
        cat "$R84_RAW_CARGO_DIR/$harness.trace"
        grep '^WORK ' "$R84_RAW_CARGO_DIR/$harness.work"
    done
    cmp "$R84_RAW_CARGO_DIR/$tier-baseline.trace" "$R84_RAW_CARGO_DIR/$tier-candidate.trace"
    cmp "$R84_RAW_CARGO_DIR/$tier-baseline.frames.jsonl" "$R84_RAW_CARGO_DIR/$tier-candidate.frames.jsonl"
done
cmp "$R84_RAW_CARGO_DIR/pin-candidate.trace" "$R84_RAW_CARGO_DIR/after407-candidate.trace"
cmp "$R84_RAW_CARGO_DIR/pin-candidate.frames.jsonl" "$R84_RAW_CARGO_DIR/after407-candidate.frames.jsonl"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo 'PASS source owners, exact content queue and admitted Render frames. No native GPUI or extension process.'
