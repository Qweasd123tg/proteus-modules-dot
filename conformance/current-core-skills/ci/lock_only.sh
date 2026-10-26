#!/usr/bin/env bash
# Authored resolution only: no Rust builds, tests, binaries or dependency scripts.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
module="${PORTABLE_SKILLS_PACKAGE:?absolute unchanged portable package}"
out="${PROBE_RESULTS_DIR:?fresh absolute output directory}"
[[ "$module" = /* && "$out" = /* ]] || exit 2
mkdir "$out"
export PYTHONDONTWRITEBYTECODE=1 CARGO_TERM_COLOR=never
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
python3 -B -I ci/source_manifest.py "$module" > "$out/source-hashes-before.json"
cp Cargo.lock "$out/baseline-host.lock"
cp "$module/Cargo.lock" "$out/unchanged-portable.lock"
run toolchain-install rustup toolchain install 1.95.0 --profile minimal --component rustfmt --no-self-update
{ rustc --version --verbose; cargo --version --verbose; } > "$out/toolchain.txt" 2>&1
run resolve timeout 300 cargo update --workspace
cp Cargo.lock "$out/resolved-host.lock"
run host-fetch timeout 300 cargo fetch --locked
run portable-fetch timeout 300 cargo fetch --locked --manifest-path "$module/Cargo.toml"
run host-metadata cargo metadata --locked --offline --format-version 1
run portable-metadata cargo metadata --locked --offline --format-version 1 --manifest-path "$module/Cargo.toml"
# Resolution may change only the variant lock. Original package/module stay frozen.
python3 -B -I - "$out/source-hashes-before.json" "$module" <<'PY'
import hashlib, json, pathlib, sys
before = json.loads(pathlib.Path(sys.argv[1]).read_text())
for kind, root in [('harness', pathlib.Path.cwd()), ('portable_module', pathlib.Path(sys.argv[2]))]:
    for name, sha in before[kind].items():
        if kind == 'harness' and name == 'Cargo.lock':
            continue
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == sha, (kind, name)
print('Only variant Cargo.lock may differ; portable and other frozen sources unchanged')
PY
printf 'lock-resolution-only; no compile or runtime; review required\n' > "$out/scope.txt"
printf 'passed\n' > "$out/status.txt"
