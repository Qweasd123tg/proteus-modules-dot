#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
R=$(pwd); B=$R/r20-bench
export PYTHONDONTWRITEBYTECODE=1
size=${SIZE:-big}
if [ "$size" = big ]; then
 golden=$R/r17-bounds/fixture-big; expected=2c24c1898a8593186328dd91fff646aa0f809758d0396c9ce959fd4488d1e375
elif [ "$size" = tiny ]; then
 golden=$R/r19-bench/tiny; expected=$(python3 "$R/r19-bench/stand/inspect_fixture.py" "$golden" | python3 -c 'import json,sys;print(json.load(sys.stdin)["archives_canonical_sha256"])')
else exit 1; fi
exec python3 "$B/stand/archives.py" --source "$R/r19-root/core" --core "${CORE_BIN:-$R/r19-root/bin/core-stock}" \
 --worker "${WORKER_BIN:-$R/r19-root/bin/worker-stock}" --core-commit "${CORE_COMMIT:-048378da7cbe890d8bf8a0152e55eb28ecb5013d}" \
 --core-sha256 "${CORE_SHA:-108a024d2edad562490d1c475b38b454151cfa1398ff6f569cc27beaf9e5e208}" \
 --worker-sha256 "${WORKER_SHA:-d9929cc7592c7c5f537b8a9c63b8cb5d09ae5a6ffc7c7306e48940bcb4c7c44e}" \
 --reference "$R/r16-cancel/target/debug/proteus-reference-module" --golden "$golden" --expected-corpus "$expected" \
 --case-path "${CASE_PATH:-$B/live-$size}" --prime-core "$R/r19-root/bin/core-stock" --prime-sha 108a024d2edad562490d1c475b38b454151cfa1398ff6f569cc27beaf9e5e208 --state "$1" --out "${OUT:-$B/evidence/$2}" "${@:3}"
