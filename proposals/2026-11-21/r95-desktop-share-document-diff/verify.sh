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
    987ff5ad1667b68d3c5d3aa5e561a398d5c7cb11adccef98d868cf6627aa4e33 "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R95_BUILD_LOCK:?shared compiler lock}"
    : "${R95_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R95_RAW_CARGO_DIR ]]
    exec 9< "$R95_BUILD_LOCK"
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
assert any(r[0]=="proteus-contracts" and r[2].endswith("#7cbc7206f03fac130d05bed2844de275476fedc8") for r in chosen)
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
chat=src/ui/chat
u=src/ui/extensions/declarative
changed=(src/declarative/widget.rs "$u"/fields.rs src/ui/diff/mod.rs)
base_files=("src/declarative" "$u"/{fields,tree,view,rich_text,terminal,inline_content,content}.rs "$u"/content/tests.rs crates/{diff,terminal} "$chat"/thread.rs src/ui/diff/{mod,file}.rs src/ui/terminal/{cells,view}.rs LICENSE-GPL)
others=(src/api/mod.rs src/ui/chats.rs "$chat"/{history,stamp,replies,session,actions,attachment_io,attachments,feedback/mod}.rs src/transcript/mod.rs "$u"/{badge.rs,runtime.rs,runtime/content_queue.rs})
mkdir pin after417
git -C "$repo" archive "$base" "${base_files[@]}" | tar xf - -C pin
(cd "$tree"; tar cf - "${base_files[@]}" "${others[@]}") | tar xf - -C after417
while IFS= read -r patch; do
    git -C after417 apply --check "$patch"
    git -C after417 apply "$patch"
done < predecessors
echo "PASS both exact predecessor stacks admitted"
for tier in pin after417; do
    git -C "$tier" init -q
    git -C "$tier" add src crates
    git -C "$tier" apply --check --index "$here/source.patch"
    for arm in baseline candidate; do
        harness="$tier-$arm"
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
            for path in "${changed[@]}"; do rustfmt --edition 2024 --config skip_children=true --check "$tier/$path"; done
        fi
        python3 "$here/materialize.py" "$tier" "$harness" "$here" > "$harness.contexts"

    done
    cmp "$tier-baseline.contexts" "$tier-candidate.contexts"
    diff -r --no-dereference "$tier-baseline/crates/diff" "$tier-candidate/crates/diff"
    echo "PASS $tier apply/reverse/whitespace/rustfmt, exact unchanged diff parser, metadata/viewport/selection methods, per-file callback and rest of rendering"
done
cmp <(grep -Ev ' (per-file-render|diff-parser|other-fields)$' pin-baseline.contexts) <(grep -Ev ' (per-file-render|diff-parser|other-fields)$' after417-baseline.contexts)
for side in baseline candidate; do
    cmp "pin-$side/src/diff.inc.rs" "after417-$side/src/diff.inc.rs"
    cmp "pin-$side/src/fields.inc.rs" "after417-$side/src/fields.inc.rs"
    cmp "pin-$side/src/copy-all.inc.rs" "after417-$side/src/copy-all.inc.rs"
done
echo 'PASS exact full-document handoff across stock and cumulative, each with its own inherited per-file callback/parser'
if [[ $mode == --prepare ]]; then
    echo 'PREPARED only. No runtime, timing, or native testing.'
    exit 0
fi
name=desktop-document-diff-probe
for tier in pin after417; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        fence
        (
            cd "$harness"
            export R95_DIFF_ARM="$stamp"
            touch src/{main.rs,diff.inc.rs,declarative/widget.rs} crates/diff/src/{lib,parse,tests}.rs
            python3 "$here/cargo_evidence.py" --snapshot . > "$R95_RAW_CARGO_DIR/$harness.inputs"
            status=0
            cargo test --offline --locked -j1 --no-run -p proteus-diff --lib --message-format=json > "$R95_RAW_CARGO_DIR/$harness.unit.cargo-json" 2> "$R95_RAW_CARGO_DIR/$harness.unit.cargo-stderr" || status=$?
            if (( status != 0 )); then
                cat "$R95_RAW_CARGO_DIR/$harness.unit.cargo-stderr"
                exit "$status"
            fi
            fence
            python3 "$here/unit_evidence.py" unit "$stamp" . "$R95_RAW_CARGO_DIR/$harness.unit" "$here/source.patch"
            grep '^test result: ok\.' "$R95_RAW_CARGO_DIR/$harness.unit.stdout" | sed -E 's/; finished in.*$//'
            status=0
            cargo build --offline --locked -j1 --message-format=json --bin "$name" > "$R95_RAW_CARGO_DIR/$harness.cargo-json" 2> "$R95_RAW_CARGO_DIR/$harness.cargo-stderr" || status=$?
            if (( status != 0 )); then
                cat "$R95_RAW_CARGO_DIR/$harness.cargo-stderr"
                python3 - "$R95_RAW_CARGO_DIR/$harness.cargo-json" <<'DIAG'
import json,sys
for line in open(sys.argv[1]):
    record=json.loads(line)
    if record.get('reason')=='compiler-message':
        print(record['message'].get('rendered') or record['message'].get('message',''))
DIAG
                exit "$status"
            fi
            fence
            python3 "$here/cargo_evidence.py" "$stamp" . "$R95_RAW_CARGO_DIR/$harness.cargo-json" "$R95_RAW_CARGO_DIR/$harness.trace" "$R95_RAW_CARGO_DIR/$harness.work" "$here/source.patch"
        )
        grep -Fx "ARM $stamp" "$R95_RAW_CARGO_DIR/$harness.work"
        cat "$R95_RAW_CARGO_DIR/$harness.trace"
        grep '^WORK ' "$R95_RAW_CARGO_DIR/$harness.work"
    done
    cmp "$R95_RAW_CARGO_DIR/$tier-baseline.trace" "$R95_RAW_CARGO_DIR/$tier-candidate.trace"
done
cmp "$R95_RAW_CARGO_DIR/pin-candidate.trace" "$R95_RAW_CARGO_DIR/after417-candidate.trace"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo 'PASS exact Diff typed and native-seam body, parser tests, whole-vs-file copy and ownership; no native GPUI.'
