#!/usr/bin/env bash
# Verify history-model behavior at the pinned revision without building GPUI.
# Expects rustc and cached .rlibs for that checkout's Cargo.lock (see README).
set -euo pipefail
ROOT=$(realpath "${1:?path to Proteus-desktop}")
DEPS=$(realpath "${2:?path to cached Cargo debug/deps}")
HERE=$(cd "$(dirname "$0")" && pwd)
PIN=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
S=$(mktemp -d "${TMPDIR:-/tmp}/history-keys.XXXXXX")
trap 'rm -rf -- "$S"' EXIT
mkdir -p "$S"/{base,patch,model}
git -C "$ROOT" archive "$PIN" src/transcript src/agents/codex/types.rs \
    src/ui/chat/history.rs src/ui/chat/history/{context,tests}.rs src/ui/chat/scroller/scrollbar.rs | tar -xC "$S/base"
cp -R "$S/base/src" "$S/patch/"
(cd "$S/patch" && git apply --check "$HERE/source.patch" && git apply "$HERE/source.patch" && git apply --reverse --check "$HERE/source.patch")
echo "git apply/check/reverse: OK @ $PIN"
rustc --version
# Explicit paths can be overridden for equivalent builds on another machine.
contracts=${CONTRACTS_RLIB:-$DEPS/libproteus_contracts-176a962a9e3c4db4.rlib}
json=${JSON_RLIB:-$DEPS/libserde_json-9aca34a9012bed43.rlib}
uuid=${UUID_RLIB:-$DEPS/libuuid-df68f608f8328002.rlib}
for arm in base patch; do
    python3 "$HERE/model_check.py" "$S/$arm" "$S/model" "$S/patch/src/ui/chat/history/tests.rs"
    rustc --edition=2024 --test --crate-name history_check -C strip=symbols -C link-arg=-fuse-ld=lld \
       -L "dependency=$DEPS" --extern "proteus_contracts=$contracts" --extern "serde_json=$json" --extern "uuid=$uuid" \
       "$S/model/check.rs" -o "$S/model/check"
    echo "=== $arm ==="
    if "$S/model/check" --test-threads=1 > "$S/$arm.log" 2>&1; then code=0; else code=$?; fi
    sed "s|$S|<temporary-test-root>|g" "$S/$arm.log"
    if [[ $arm == base ]]; then
        [[ $code == 101 ]]
        grep -Fq '58 passed; 2 failed' "$S/base.log"
        for test in distant_seek_windows_never_alias_other_rows paging_forward_from_seek_preserves_only_real_live_overlap; do
            grep -Fq "test history::tests::$test ... FAILED" "$S/base.log"
        done
    else
        [[ $code == 0 ]]
        grep -Fq '60 passed; 0 failed' "$S/patch.log"
    fi
done
