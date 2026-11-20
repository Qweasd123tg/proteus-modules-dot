#!/bin/bash
# Same synthetic corpus, same absolute case path, strictly serial runs.
set -euo pipefail
cd "$(dirname "$0")/.."
R=$PWD; D="$R/r22"; name="$1"; worker="$(realpath "$2")"
[[ "$name" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*$ ]]
[[ -x "$worker" ]]
export PYTHONDONTWRITEBYTECODE=1
prime="$R/r19-root/bin/core-stock"
core="$(realpath "${CORE_BIN:-$prime}")"
read -r sha _ < <(sha256sum "$worker")
prime_sha=108a024d2edad562490d1c475b38b454151cfa1398ff6f569cc27beaf9e5e208
if [[ "$core" == "$prime" ]]; then core_sha="$prime_sha"; else read -r core_sha _ < <(sha256sum "$core"); fi
wire=()
if [[ "${WIRE:-no}" == yes ]]; then wire=(--wire); fi
if [[ "$(basename "$worker")" == *-trace && "${#wire[@]}" -ne 1 ]]; then
  echo 'Tracing requires WIRE=yes to pass diagnostic settings to the worker' >&2; exit 2
fi
exec flock -n "$D/.bench-lock" python3 "$D/stand/archives.py" \
  --source "$R/r19-root/core" --core "$core" --worker "$worker" \
  --core-commit 048378da7cbe890d8bf8a0152e55eb28ecb5013d \
  --core-sha256 "$core_sha" --worker-sha256 "$sha" \
  --reference "$R/r16-cancel/target/debug/proteus-reference-module" \
  --golden "$R/r17-bounds/fixture-big" --expected-corpus 2c24c1898a8593186328dd91fff646aa0f809758d0396c9ce959fd4488d1e375 \
  --case-path "$D/live-case" --prime-core "$prime" --prime-sha "$prime_sha" \
  --state absent --out "$D/runs/$name" --desktop-bridge "$R/r20-desktop/desktop_api.py" "${wire[@]}"
