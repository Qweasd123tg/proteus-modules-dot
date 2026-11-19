#!/bin/sh
set -eu
# $1 = full Desktop git checkout. $2 = fresh, empty output directory.
src=$(cd "$1"; pwd)
mkdir -p "$2"
out=$(cd "$2";pwd)
test -z "$(ls -A "$out")"
here=$(cd "$(dirname "$0")";pwd)
pin=210cc9f274ffe40533b390a0d9e940f251a9fa22
export CARGO_TARGET_DIR="$out/target"
cp "$here/run.py" "$here/peer.py" "$out/"
for v in stock after; do
  work="$out/$v"
  mkdir -p "$work"
  git -C "$src" archive "$pin" -- src/transcript src/agents/codex/router.rs src/agents/codex/types.rs src/agents/codex/projection.rs src/ui/chat/codex/mod.rs crates/codex-client | tar -x -C "$work"
  cp "$here/Cargo.toml" "$here/Cargo.lock" "$work/"
  sed 's/cfg(not(fast))/cfg(not(feature = "fast"))/g;s/cfg(fast)/cfg(feature = "fast")/g' "$here/bench.rs" > "$work/src/main.rs"
  if test "$v" = after; then
    (cd "$work";git apply --check "$here/codex-tail.patch";git apply "$here/codex-tail.patch")
    features=fast
  else
    features=""
  fi
  (cd "$work"; cargo test --locked --release --features "$features" -- --test-threads=1) > "$out/$v-tests.log"
  (cd "$work"; cargo build --locked --release --features "$features")
  cp "$CARGO_TARGET_DIR/release/codex-tail-probe" "$out/$v-executable"
done
(cd "$out";python3 run.py > series.txt)
