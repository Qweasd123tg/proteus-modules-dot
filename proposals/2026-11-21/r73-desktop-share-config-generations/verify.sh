#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 6 || ( "$1" != --prepare && "$1" != --run ) ]]; then
    echo 'usage: bash verify.sh [--prepare|--run] DESKTOP_GIT SEALED_M150 SOURCE_SEAL PATCH_393 CUMULATIVE_PATCH_396' >&2
    exit 2
fi
mode=$1
here=$(cd "$(dirname "$0")" && pwd)
repo=$(realpath "$2")
tree=$(realpath "$3")
seal=$(realpath "$4")
history=$(realpath "$5")
page_text=$(realpath "$6")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
printf '%s  %s\n' \
    25115b6fb01b930096807d6747e2ee7d71993488db8294413cc1cd4498e4fe95 "$seal" \
    87c96e53a64f765f60599998ffb0e9d0374b56e60e5f1bfc1827259d458e32ea "$history" \
    7e15342d0cae2a391f91e45f86a61d28a212533caddaf161b969cae1be88ceef "$page_text" | sha256sum -c --status
python3 "$here/seal_check.py" "$tree" "$seal"
if [[ $mode == --run ]]; then
    : "${CARGO_HOME:?set to the existing locked offline cache}"
    : "${CARGO_TARGET_DIR:?set to the existing warm Desktop target}"
    [[ -d $CARGO_HOME && -d $CARGO_TARGET_DIR ]]
    [[ $(df -Pk "$CARGO_TARGET_DIR" | awk 'NR==2{print $4}') -ge 524288 ]]
    export CARGO_INCREMENTAL=0 CARGO_NET_OFFLINE=true
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
print(f"PASS {len(chosen)} locked dependency identities and exact contracts")
PY
p=src
paths=("$p/declarative/session.rs" "$p/declarative/manifest.rs" "$p/declarative/protocol.rs" "$p/ui/chat/actions.rs" "$p/ui/chat/session.rs" "$p/ui/chat/context_usage.rs" "$p/ui/chat/history.rs" "$p/transcript/mod.rs" "$p/ui/extensions/session.rs" "$p/ui/extensions/host.rs" "$p/ui/extensions/host/scope.rs" "$p/ui/extensions/declarative/runtime/scopes.rs")
for tier in pin after396; do
    mkdir "$tier"
    if [[ $tier == pin ]]; then
        git -C "$repo" archive "$base" "${paths[@]}" | tar xf - -C "$tier"
    else
        (cd "$tree"; tar cf - "${paths[@]}") | tar xf - -C "$tier"
        for predecessor in "$history" "$page_text"; do
            git -C "$tier" apply --check "$predecessor"
            git -C "$tier" apply "$predecessor"
        done
    fi
    git -C "$tier" init -q
    git -C "$tier" add "$p"
    git -C "$tier" apply --index --check "$here/source.patch"
    for arm in baseline candidate; do
        harness="$tier-$arm"
        mkdir -p "$harness/src"
        if [[ $arm == candidate ]]; then
            git -C "$tier" apply "$here/source.patch"
            git -C "$tier" apply --reverse --check "$here/source.patch"
            git -C "$tier" diff --check
        fi
        cp "$tier/$p/declarative/session.rs" "$harness/src/session.rs"
        cp "$here/probe.rs" "$harness/src/main.rs"
        python3 "$here/materialize.py" "$tier" "$harness"
        cp "$here/harness.toml" "$harness/Cargo.toml"
        cp "$here/harness.lock" "$harness/Cargo.lock"
    done
    printf 'PASS %s apply, reverse, whitespace, exact DTO materialization\n' "$tier"
done
cmp pin-candidate/src/session.rs after396-candidate/src/session.rs
echo 'PASS identical resulting projection source at both tiers'
if [[ $mode == --prepare ]]; then
    echo 'HOLD: stopped after static preparation, no Cargo, tests or probe executed.'
    exit 0
fi
name=desktop-config-share-probe
for tier in pin after396; do
    for arm in baseline candidate; do
        harness="$tier-$arm"
        stamp="$tier/$arm"
        (
            cd "$harness"
            export R73_CONFIG_PROBE_ARM="$stamp"
            touch src/main.rs src/session.rs
            cargo build --offline --locked -j1 --message-format=json --bin "$name" > "../$harness.cargo-json" 2> "../$harness.cargo-stderr"
            if [[ -n ${R73_RAW_CARGO_DIR:-} ]]; then
                cp "../$harness.cargo-json" "../$harness.cargo-stderr" "$R73_RAW_CARGO_DIR/"
            fi
            python3 "$here/cargo_evidence.py" "$stamp" . "../$harness.cargo-json" "../$harness.wire" "../$harness.work" "$here/source.patch"
        )
        grep -Fx "ARM $stamp" "$harness.work"
        grep -E '^(WORK|ROUTES) ' "$harness.work"
    done
    cmp "$tier-baseline.wire" "$tier-candidate.wire"
    sha256sum "$tier-candidate.wire"
done
cmp pin-candidate.wire after396-candidate.wire
python3 "$here/seal_check.py" "$tree" "$seal"
echo 'PASS exact projected Desktop snapshot/update frame bytes and exercised routes; GPUI and live transport not run.'
