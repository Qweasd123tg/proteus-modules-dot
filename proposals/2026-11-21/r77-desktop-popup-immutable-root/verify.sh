#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 8 || ( "$1" != --prepare && "$1" != --run ) ]]; then
    echo 'usage: bash verify.sh [--prepare|--run] DESKTOP_GIT SEALED_M150 SOURCE_SEAL PATCH_393 CUMULATIVE_PATCH_396 PATCH_398 PATCH_400' >&2
    exit 2
fi
mode=$1
here=$(cd "$(dirname "$0")" && pwd)
repo=$(realpath "$2")
tree=$(realpath "$3")
seal=$(realpath "$4")
h=$(realpath "$5")
p=$(realpath "$6")
c=$(realpath "$7")
s=$(realpath "$8")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
printf '%s  %s\n' \
    25115b6fb01b930096807d6747e2ee7d71993488db8294413cc1cd4498e4fe95 "$seal" \
    87c96e53a64f765f60599998ffb0e9d0374b56e60e5f1bfc1827259d458e32ea "$h" \
    7e15342d0cae2a391f91e45f86a61d28a212533caddaf161b969cae1be88ceef "$p" \
    897d3a261fa0da254f324a8acad4d51c5f33019b83370734d9bc59c74c3943a0 "$c" \
    50bec985641b0231497394cf1f507f739464b93c975c4a95469ad9c34f1310aa "$s" \
    af9081a70781c52ab1cdd55435c4256c2e4abb49fb4a23c42794ef48b7edaa74 "$here/source.patch" \
    | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?existing warm Desktop target}"
    : "${R77_BUILD_LOCK:?shared compiler lock}"
    : "${R77_RAW_CARGO_DIR:?existing raw output directory}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR && -d $R77_RAW_CARGO_DIR ]]
    exec 9< "$R77_BUILD_LOCK"
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
git -C "$repo" show "$base:Cargo.lock" > upstream.lock
cmp upstream.lock "$tree/Cargo.lock"
python3 - "$here/harness.lock" <<'PY'
from pathlib import Path
import sys,tomllib
def identities(path):
    data=tomllib.loads(Path(path).read_text())
    return {(r["name"],r["version"],r["source"],r.get("checksum")) for r in data["package"] if "source" in r}
chosen=identities(sys.argv[1])
assert chosen <= identities("upstream.lock")
assert any(r[0]=="proteus-contracts" and r[2].endswith("#7cbc7206f03fac130d05bed2844de275476fedc8") for r in chosen)
print(f"PASS {len(chosen)} Desktop Cargo.lock dependency identities; exact local proteus-diff source")
PY
u=src/ui/extensions/declarative
d=src/declarative
m=src/ui/motion
paths=("$u/badge.rs" "$u/view.rs" "$u/popup.rs" "$u/runtime.rs" "$u/images.rs" "$u/fields.rs" "$m/popup.rs" "$m/mod.rs" "$d" crates/diff src/api/mod.rs src/ui/chat/history.rs src/transcript/mod.rs src/ui/chat/actions.rs src/ui/chat/session.rs)
for tier in pin after400; do
    mkdir "$tier"
    if [[ $tier == pin ]]; then
        git -C "$repo" archive "$base" "${paths[@]}" | tar xf - -C "$tier"
    else
        (cd "$tree"; tar cf - "${paths[@]}") | tar xf - -C "$tier"
        for predecessor in "$h" "$p" "$c" "$s"; do
            git -C "$tier" apply --check "$predecessor"
            git -C "$tier" apply "$predecessor"
        done
    fi
    git -C "$tier" init -q
    git -C "$tier" add src crates
    git -C "$tier" apply --index --check "$here/source.patch"
    for arm in baseline candidate; do
        harness="$tier-$arm"
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
        fi
        python3 "$here/materialize.py" "$tier" "$harness" "$here" > "$harness.contexts"
        python3 "$here/future-fixtures.py" > "$harness/src/fixtures.jsonl"
    done
    cmp "$tier-baseline.contexts" "$tier-candidate.contexts"
    diff -r "$tier-baseline/crates/diff" "$tier-candidate/crates/diff" --no-dereference
    printf 'PASS %s apply/reverse/whitespace, unchanged render/callback contexts and local diff crate\n' "$tier"
done
cmp pin-baseline.contexts after400-baseline.contexts
echo 'PASS same popup/render/callback context hashes at both tiers'
if [[ $mode == --prepare ]]; then
    echo 'PREPARED: no Cargo, tests or probe executed.'
    exit 0
fi
name=desktop-popup-probe
for tier in pin after400; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        fence
        (
            cd "$harness"
            export R77_POPUP_PROBE_ARM="$stamp"
            touch src/main.rs src/carrier.rs src/view.inc.rs
            status=0
            cargo build --offline --locked -j1 --message-format=json --bin "$name" > "$R77_RAW_CARGO_DIR/$harness.cargo-json" 2> "$R77_RAW_CARGO_DIR/$harness.cargo-stderr" || status=$?
            if (( status != 0 )); then
                cat "$R77_RAW_CARGO_DIR/$harness.cargo-stderr"
                python3 - "$R77_RAW_CARGO_DIR/$harness.cargo-json" <<'DIAG'
import json,sys
for line in open(sys.argv[1]):
    record=json.loads(line)
    if record.get('reason')=='compiler-message':
        print(record['message'].get('rendered') or record['message'].get('message',''))
DIAG
                exit "$status"
            fi
            fence
            python3 "$here/cargo_evidence.py" "$stamp" . "$R77_RAW_CARGO_DIR/$harness.cargo-json" "$R77_RAW_CARGO_DIR/$harness.trace" "$R77_RAW_CARGO_DIR/$harness.work" "$here/source.patch"
        )
        grep -Fx "ARM $stamp" "$R77_RAW_CARGO_DIR/$harness.work"
        cat "$R77_RAW_CARGO_DIR/$harness.trace"
        grep '^WORK ' "$R77_RAW_CARGO_DIR/$harness.work"
    done
    cmp "$R77_RAW_CARGO_DIR/$tier-baseline.trace" "$R77_RAW_CARGO_DIR/$tier-candidate.trace"
done
cmp "$R77_RAW_CARGO_DIR/pin-candidate.trace" "$R77_RAW_CARGO_DIR/after400-candidate.trace"
python3 "$here/seal_check.py" "$tree" "$seal"
fence
echo 'PASS exact parser, close/reopen methods and lifetime / identity / action assertions, no native GPUI.'
