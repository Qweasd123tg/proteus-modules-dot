#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
if [[ $# -ne 3 ]]; then
  printf 'usage: %s EXACT_GIT_COPY OUT_DIR EXISTING_TARGET\n' "$0" >&2
  exit 2
fi
base="$(realpath "$1")"
mkdir "$2"; out="$(realpath "$2")"
target="$(realpath "$3")"
export CARGO_TARGET_DIR="$target" CARGO_BUILD_JOBS=1 CARGO_NET_OFFLINE=true CARGO_INCREMENTAL=0
export PYTHONDONTWRITEBYTECODE=1
git -c advice.detachedHead=false clone --no-local -q "$base" "$out/main"
git -C "$out/main" -c advice.detachedHead=false checkout -q --detach 9469e3b12529d08b1f4a76882693e2065e842c51
(cd "$out/main"; git apply --check "$here/candidate.patch"; git apply "$here/candidate.patch")
python3 "$here/instrument.py" "$out/main"
(cd "$out/main" && cargo test --offline --locked --release -j1 -p session-storage --lib -- --nocapture) >"$out/native-and-measure.log" 2>&1
python3 "$here/verify.py" "$out/native-and-measure.log" > "$out/counts.json"
