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
    2d321b1ad587174baf3fec2bc2ab431ca0714184d1333b6fe8be8663a94511bb "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R91_BUILD_LOCK:?shared compiler lock}"
    : "${R91_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R91_RAW_CARGO_DIR ]]
    exec 9< "$R91_BUILD_LOCK"
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
assert any(r[0:2] == ("alacritty_terminal","0.25.1") for r in chosen)
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
chat=src/ui/chat
u=src/ui/extensions/declarative
changed=(crates/terminal/src/{display.rs,display/tests.rs} src/ui/terminal/{cells,view}.rs "$u"/terminal.rs)
base_files=("src/declarative" "$u"/{fields,tree,tree_row,menu,view}.rs crates/diff src/ui/diff/{mod,file}.rs crates/terminal src/ui/terminal/{cells,view,io,pending}.rs "$u"/terminal.rs vendor/{ghostty-vt,ghostty-vt-sys} LICENSE-GPL LICENSE-APACHE)
others=(src/api/mod.rs src/ui/chats.rs "$chat"/{history,stamp,thread,replies,session,actions,attachment_io,attachments,feedback/mod}.rs src/transcript/mod.rs "$u"/{badge.rs,content.rs,inline_content.rs,content/tests.rs,runtime.rs,runtime/content_queue.rs})
mkdir pin after413
git -C "$repo" archive "$base" "${base_files[@]}" | tar xf - -C pin
(cd "$tree"; tar cf - "${base_files[@]}" "${others[@]}") | tar xf - -C after413
while IFS= read -r patch; do
    git -C after413 apply --check "$patch"
    git -C after413 apply "$patch"
done < predecessors
echo "PASS both exact predecessor stacks admitted"
for tier in pin after413; do
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
    cmp "$tier-baseline/crates/terminal/Cargo.toml" "$tier-candidate/crates/terminal/Cargo.toml"
    echo "PASS $tier apply/reverse/whitespace/rustfmt, exact unchanged engine, transport, initial layout, cell geometry and frame policy"
done
cmp pin-baseline.contexts after413-baseline.contexts
for side in baseline candidate; do
    diff -r --no-dereference -x alacritty_screen.rs "pin-$side/crates/terminal" "after413-$side/crates/terminal"
done
echo 'PASS same focused terminal and cursor path across tiers, with real inherited #251 Alacritty run grouping'
if [[ $mode == --prepare ]]; then
    echo 'PREPARED only. No runtime, timing, or native testing.'
    exit 0
fi
cargo_phase() {
    local report=$1
    shift
    local status=0
    "$@" > "$report.cargo-json" 2> "$report.cargo-stderr" || status=$?
    if (( status != 0 )); then
        cat "$report.cargo-stderr"
        python3 - "$report.cargo-json" <<'DIAG'
import json,sys
for line in open(sys.argv[1]):
    record=json.loads(line)
    if record.get('reason')=='compiler-message':
        print(record['message'].get('rendered') or record['message'].get('message',''))
DIAG
        return "$status"
    fi
    fence
}
for tier in pin after413; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        fence
        (
            cd "$harness"
            export R91_TERMINAL_ARM="$stamp"
            touch crates/terminal/src/{lib.rs,display.rs,display/tests.rs,display/r91_fixtures.rs}
            prefix="$R91_RAW_CARGO_DIR/$harness"
            python3 "$here/cargo_evidence.py" snapshot . > "$prefix.inputs"
            cargo_phase "$prefix.unit" cargo test --offline --locked -j1 --no-default-features --no-run -p proteus-terminal --lib --message-format=json
            python3 "$here/cargo_evidence.py" unit "$stamp" . "$prefix.unit" "$here/source.patch"
        )
        stem="$R91_RAW_CARGO_DIR/$harness.unit.stdout"
        grep -E '^test result: ok\. [0-9]+ passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;' "$stem" | sed -E 's/; finished in.*$//'
        grep -Fx "ARM $stamp" "$stem"
        grep '^TRACE ' "$stem" | tee "$harness.trace"
        grep '^WORK ' "$stem"
    done
    cmp "$tier-baseline.trace" "$tier-candidate.trace"
done
cmp pin-candidate.trace after413-candidate.trace
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo 'PASS exact Alacritty unit suite, one-shot redraw, shared-frame ownership and process-finished cursor projection; no native GPUI/Ghostty.'
