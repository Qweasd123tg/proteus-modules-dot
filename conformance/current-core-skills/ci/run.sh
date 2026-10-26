#!/usr/bin/env bash
# Standalone package gate. Only authored probe/module executables are run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
module="${PORTABLE_SKILLS_PACKAGE:?set absolute path to frozen portable-skill-catalog package}"
[[ "$module" = /* ]] || { echo 'PORTABLE_SKILLS_PACKAGE must be absolute' >&2; exit 2; }
out="${PROBE_RESULTS_DIR:-$PWD/ci-results}"
mkdir -p "$(dirname "$out")"
mkdir "$out"
out="$(cd "$out" && pwd)"
export PYTHONDONTWRITEBYTECODE=1 CARGO_TERM_COLOR=never
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$PWD/target}"
[[ "$CARGO_TARGET_DIR" = /* ]] || { echo 'CARGO_TARGET_DIR must be absolute' >&2; exit 2; }
printf 'pending\n' > "$out/status.txt"
python3 -B -I ci/source_manifest.py "$module" > "$out/source-hashes.json"
{ rustc --version --verbose; cargo --version --verbose; } > "$out/toolchain.txt" 2>&1
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
run capture-controls python3 -B -I ci/test_capture_controls.py
run fmt cargo fmt --check
run module-fmt cargo fmt --check --manifest-path "$module/Cargo.toml"
run fetch timeout 300 cargo fetch --locked
run module-fetch timeout 300 cargo fetch --locked --manifest-path "$module/Cargo.toml"
run metadata cargo metadata --locked --offline --format-version 1
run module-metadata cargo metadata --locked --offline --format-version 1 --manifest-path "$module/Cargo.toml"
run module-build timeout 600 cargo build --locked --offline -j2 --manifest-path "$module/Cargo.toml"
run build timeout 900 cargo build --locked --offline -j2
run probe python3 -B -I ci/run_probe.py \
  --probe "$CARGO_TARGET_DIR/debug/proteus-portable-skills-core-probe" \
  --module "$CARGO_TARGET_DIR/debug/proteus-example-portable-skill-catalog" \
  --output "$out/probe"
python3 -B -I ci/source_manifest.py "$module" > "$out/source-hashes-after.json"
run evidence python3 -B -I ci/verify_results.py "$out/probe/stdout.json" \
  "$out/probe/stderr.txt" scenarios.json "$out/source-hashes.json" "$out/source-hashes-after.json"
printf 'passed\n' > "$out/status.txt"
