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
    4dfdc7d22ed7dc7b2b043b5a847123d375d8289edd5e4ca2de99fbd405f9201d "$here/source.patch" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R89_BUILD_LOCK:?shared compiler lock}"
    : "${R89_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R89_RAW_CARGO_DIR ]]
    exec 9< "$R89_BUILD_LOCK"
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
assert {r[0] for r in chosen} == {"serde","serde_core","serde_derive","proc-macro2","quote","syn","unicode-ident"}
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities")
PY
chat=src/ui/chat
u=src/ui/extensions/declarative
changed=(crates/diff/src/{lib,parse,tests}.rs src/ui/diff/file.rs)
base_files=("src/declarative" "$u"/{fields,tree,tree_row,menu,view}.rs crates/diff src/ui/diff/{mod,file}.rs LICENSE-GPL)
others=(src/api/mod.rs src/ui/chats.rs "$chat"/{history,stamp,thread,replies,session,actions,attachment_io,attachments,feedback/mod}.rs src/transcript/mod.rs "$u"/{badge.rs,content.rs,inline_content.rs,content/tests.rs,runtime.rs,runtime/content_queue.rs})
mkdir pin after411
git -C "$repo" archive "$base" "${base_files[@]}" | tar xf - -C pin
(cd "$tree"; tar cf - "${base_files[@]}" "${others[@]}") | tar xf - -C after411
while IFS= read -r patch; do
    git -C after411 apply --check "$patch"
    git -C after411 apply "$patch"
done < predecessors
echo "PASS both exact predecessor stacks admitted"
for tier in pin after411; do
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
    cmp "$tier-baseline/crates/diff/Cargo.toml" "$tier-candidate/crates/diff/Cargo.toml"
    echo "PASS $tier apply/reverse/whitespace/rustfmt, exact unchanged whole-diff clipboard, file header/body, and parser guards"
done
cmp pin-baseline.contexts after411-baseline.contexts
cmp pin-baseline/src/copy.inc.rs after411-baseline/src/copy.inc.rs
cmp pin-candidate/src/copy.inc.rs after411-candidate/src/copy.inc.rs
cmp pin-baseline/crates/diff/src/parse.rs after411-baseline/crates/diff/src/parse.rs
cmp pin-candidate/crates/diff/src/parse.rs after411-candidate/crates/diff/src/parse.rs
echo 'PASS exact per-file callback and parser across stock and cumulative, with each inherited local diff crate and its own unit assertions'
if [[ $mode == --prepare ]]; then
    echo 'PREPARED only. No runtime, timing, or native testing.'
    exit 0
fi
name=desktop-diff-copy-probe
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
for tier in pin after411; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        fence
        (
            cd "$harness"
            export R89_DIFF_PROBE_ARM="$stamp"
            touch src/main.rs src/copy.inc.rs crates/diff/src/{lib,parse,tests}.rs
            prefix="$R89_RAW_CARGO_DIR/$harness"
            python3 "$here/cargo_evidence.py" snapshot . > "$prefix.inputs"
            cargo_phase "$prefix.unit" cargo test --offline --locked -j1 --no-run -p proteus-diff --lib --message-format=json
            python3 "$here/cargo_evidence.py" unit "$stamp" . "$prefix.unit" "$here/source.patch"
            cargo_phase "$prefix.probe" cargo build --offline --locked -j1 --bin "$name" --message-format=json
            python3 "$here/cargo_evidence.py" probe "$stamp" . "$prefix.probe" "$here/source.patch"
        )
        grep -E "^test result: ok\. [0-9]+ passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;" "$R89_RAW_CARGO_DIR/$harness.unit.stdout"
        sed -E 's/; finished in.*$//' "$R89_RAW_CARGO_DIR/$harness.unit.stdout" | sed -E '/^$/d' > "$harness.units"
        grep -Fx "ARM $stamp" "$R89_RAW_CARGO_DIR/$harness.probe.stderr"
        cat "$R89_RAW_CARGO_DIR/$harness.probe.stdout"
        grep '^WORK ' "$R89_RAW_CARGO_DIR/$harness.probe.stderr"
    done
    cmp "$tier-baseline.units" "$tier-candidate.units"
    cmp "$R89_RAW_CARGO_DIR/$tier-baseline.probe.stdout" "$R89_RAW_CARGO_DIR/$tier-candidate.probe.stdout"
done
cmp "$R89_RAW_CARGO_DIR/pin-candidate.probe.stdout" "$R89_RAW_CARGO_DIR/after411-candidate.probe.stdout"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo 'PASS exact diff unit suite and per-file Copy callback old-generation bytes, ownership and allocation; no native clipboard.'
