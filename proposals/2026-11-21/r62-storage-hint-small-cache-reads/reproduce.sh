#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
if [[ $# -ne 5 && $# -ne 6 ]]; then
  printf 'usage: %s EXACT_GIT_COPY OUT_DIR EXISTING_TARGET STOCK_WORKER PRIVATE_R59_FIXTURE [COMPOSED_SOURCE]\n' "$0" >&2
  exit 2
fi
base="$(realpath "$1")"
mkdir "$2"; out="$(realpath "$2")"
target="$(realpath "$3")"
stock="$(realpath "$4")"
fixture="$(realpath "$5")"
export CARGO_TARGET_DIR="$target" CARGO_BUILD_JOBS=1 CARGO_NET_OFFLINE=true CARGO_INCREMENTAL=0
export PYTHONDONTWRITEBYTECODE=1
git clone --no-local -q "$base" "$out/main"
git -C "$out/main" checkout -q --detach 9469e3b12529d08b1f4a76882693e2065e842c51
(cd "$out/main"; git apply --check "$here/candidate.patch"; git apply "$here/candidate.patch")
(cd "$out/main" && cargo test --offline --locked --release -j1 -p session-storage --lib) >"$out/native.log" 2>&1
python3 "$here/instrument.py" "$out/main"
(cd "$out/main" && cargo build --offline --locked --release -j1 -p proteus-session-storage-module) >"$out/build-meter.log" 2>&1
cp "$target/release/proteus-session-storage-module" "$out/worker-meter"
python3 "$here/measure.py" "$fixture" "$stock" "$out/worker-meter" "$out/main-counts.json"
if [[ $# -eq 6 ]]; then
  cp -a "$(realpath "$6")" "$out/composed"
  (cd "$out/composed"; git apply --check "$here/candidate-cumulative.patch"; git apply "$here/candidate-cumulative.patch")
  python3 "$here/instrument.py" "$out/composed"
  (cd "$out/composed" && cargo build --offline --locked --release -j1 -p proteus-session-storage-module) >"$out/build-composed.log" 2>&1
  cp "$target/release/proteus-session-storage-module" "$out/worker-composed"
  python3 "$here/measure.py" "$fixture" "$stock" "$out/worker-composed" "$out/composed-counts.json"
fi
