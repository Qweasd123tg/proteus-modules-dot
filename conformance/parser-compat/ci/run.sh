#!/usr/bin/env bash
# Only authored comparison/control executables, never upstream parser suites.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
out="${PROBE_RESULTS_DIR:-$PWD/ci-results}"
mkdir -p "$(dirname "$out")"
mkdir "$out"
out="$(cd "$out" && pwd)"
export PYTHONDONTWRITEBYTECODE=1 CARGO_TERM_COLOR=never
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$PWD/target}"
[[ "$CARGO_TARGET_DIR" = /* ]] || { echo 'CARGO_TARGET_DIR must be absolute' >&2; exit 2; }
printf 'pending\n' > "$out/status.txt"
trap 'code=$?; if (( code != 0 )) && [[ "$(cat "$out/status.txt")" == pending ]]; then printf "failed:preflight-or-finalization:%s\n" "$code" > "$out/status.txt"; fi' EXIT
python3 -B -I ci/source_manifest.py > "$out/source-hashes.json"
# This output exists only after a fresh leaf and successful current input receipt.
# A stale leaf fails mkdir above and never makes its old files eligible for upload.
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then printf 'fresh_results=true\n' >> "$GITHUB_OUTPUT"; fi
{ rustc --version --verbose; cargo --version --verbose; python3 --version; } > "$out/toolchain.txt" 2>&1
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
run verifier-controls python3 -B -I ci/test_verifiers.py
run capture-controls python3 -B -I ci/test_capture_controls.py
run guard-controls python3 -B -I ci/test_guard_controls.py
run helper-log-controls python3 -B -I ci/test_helper_log_controls.py
run helper-coverage python3 -B -I ci/verify_helper_logs.py "$out" ci/required-helper-tests.json
run fmt cargo fmt --check
run fetch python3 -B -I ci/guarded_cargo.py fetch --output "$out/guarded-fetch"
run metadata cargo metadata --locked --offline --format-version 1
run dependency-identity python3 -B -I ci/verify_metadata.py "$out/metadata.stdout"
run build python3 -B -I ci/guarded_cargo.py build --output "$out/guarded-build"
run comparison timeout 960 python3 -B -I ci/run_comparison.py \
  --binary "$CARGO_TARGET_DIR/debug/proteus-typed-frontmatter-comparison" --output "$out/comparison"
python3 -B -I ci/source_manifest.py > "$out/source-hashes-after.json"
run source-unchanged cmp "$out/source-hashes.json" "$out/source-hashes-after.json"
printf 'passed_observation_and_control_integrity_not_migration\n' > "$out/status.txt"
