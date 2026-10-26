#!/usr/bin/env bash
# Authored package gate; executes no upstream harness/server test suite.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
out="${PROBE_RESULTS_DIR:-$PWD/ci-results}"
# Atomic fresh leaf: never mix a new attempt with stale evidence.
mkdir -p "$(dirname "$out")"
mkdir "$out"
export PYTHONDONTWRITEBYTECODE=1 CARGO_TERM_COLOR=never
python3 -B -I ci/source_manifest.py > "$out/source-hashes.json"
{ rustc --version --verbose; cargo --version --verbose; } > "$out/toolchain.txt" 2>&1
printf 'pending\n' > "$out/status.txt"
run() {
  local name="$1"; shift
  printf '%q ' "$@" > "$out/$name.command"; printf '\n' >> "$out/$name.command"
  set +e
  "$@" > "$out/$name.stdout" 2> "$out/$name.stderr"
  local code=$?
  set -e
  printf '%s\n' "$code" > "$out/$name.exit"
  cat "$out/$name.stdout"; cat "$out/$name.stderr" >&2
  if (( code != 0 )); then printf 'failed:%s:%s\n' "$name" "$code" > "$out/status.txt"; exit "$code"; fi
}
run source-freeze sha256sum -c CODE.sha256
run verifier-controls python3 -B -I ci/test_verify_results.py
run fmt cargo fmt --check
run fetch timeout 240 cargo fetch --locked
run metadata cargo metadata --locked --offline --format-version 1
run tests timeout 240 cargo test --locked --offline --all-targets -- --test-threads=1
python3 -B -I ci/source_manifest.py > "$out/source-hashes-after.json"
run evidence python3 -B -I ci/verify_results.py "$out/tests.stdout" ci/required-tests.json "$out/source-hashes.json" "$out/source-hashes-after.json"
printf 'passed\n' > "$out/status.txt"
