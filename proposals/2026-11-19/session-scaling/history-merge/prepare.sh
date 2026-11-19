#!/bin/bash
set -eu
here=$(cd "$(dirname "$0")" && pwd)
desktop=$(realpath "${1:?pass a clean pinned Desktop checkout}")
[ "$(git -C "$desktop" rev-parse HEAD)" = 210cc9f274ffe40533b390a0d9e940f251a9fa22 ]
git -C "$desktop" diff --exit-code HEAD -- src/transcript src/agents/codex/types.rs >/dev/null
out=${2:?choose a new work directory}; mkdir "$out"; out=$(realpath "$out")
cp "$here"/{harness.rs,build.sh,run.sh,summary.py} "$out"
for v in base after; do
 mkdir -p "$out/$v/src"; cp -R "$desktop/src/transcript" "$out/$v/src"; cp "$desktop/src/agents/codex/types.rs" "$out/$v/src/codex.rs"
done
git -C "$out/after" apply --no-index --check --whitespace=error "$here/index-history.patch"
git -C "$out/after" apply --no-index "$here/index-history.patch"
echo "Prepared $out; next: DEPS=/absolute/matching/release/deps bash '$out/build.sh'; BENCH_CPU=<allowed-core> bash '$out/run.sh'; python3 '$out/summary.py'"
