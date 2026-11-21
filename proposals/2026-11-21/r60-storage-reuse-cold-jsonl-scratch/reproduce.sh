#!/usr/bin/env bash
# Exact local validation, no elapsed timings. Choose new writable paths.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
if [[ $# -ne 6 ]]; then
  printf 'usage: %s EXACT_GIT_COPY COMPOSED_SOURCE_DIR OUT_DIR CACHED_TARGET STOCK_WORKER M100_WORKER\n' "$0" >&2
  exit 2
fi
base="$(realpath "$1")"
composition="$(realpath "$2")"
mkdir "$3"
out="$(realpath "$3")"
target="$(realpath "$4")"
stock="$(realpath "$5")"
m100="$(realpath "$6")"
export CARGO_TARGET_DIR="$target" CARGO_BUILD_JOBS=1 CARGO_NET_OFFLINE=true CARGO_INCREMENTAL=0
export PYTHONDONTWRITEBYTECODE=1
git clone --no-local -q "$base" "$out/main"
git -C "$out/main" checkout -q --detach 9469e3b12529d08b1f4a76882693e2065e842c51
cp -a "$composition" "$out/composed"
for tuple in 'main:candidate.patch' 'composed:candidate-after-256.patch'; do
  arm="${tuple%%:*}"
  patch="$here/${tuple#*:}"
  (cd "$out/$arm"; git apply --check "$patch"; git apply "$patch")
done
(cd "$out/main" && cargo test --offline --locked --release -j1 -p session-storage --lib) >"$out/native-main.log" 2>&1
python3 "$here/fixture.py" jsonl125k "$stock" "$out/fresh-125k" >"$out/seed.log"
for arm in main composed; do
  cp -a "$out/$arm" "$out/$arm-meter"
  python3 "$here/instrument.py" "$out/$arm-meter"
  (
    cd "$out/$arm-meter"
    cargo build --offline --locked --release -j1 -p proteus-session-storage-module
  ) >"$out/build-$arm-meter.log" 2>&1
  cp "$target/release/proteus-session-storage-module" "$out/worker-$arm"
  if [[ "$arm" = main ]]; then reference="$stock"; comp=main; else reference="$m100"; comp=after-256; fi
  python3 "$here/measure.py" "$out/fresh-125k" "$reference" "$out/worker-$arm" "$out/$arm-alloc.json" --composition "$comp"
done
