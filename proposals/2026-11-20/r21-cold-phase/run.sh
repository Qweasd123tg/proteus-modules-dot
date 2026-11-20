#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
R=$PWD; N=$R/r21-cold; arm="$1"; name="$2"; size="${SIZE:-big}"
case "$arm" in
stock) worker="$R/r19-root/bin/worker-stock"; sha=d9929cc7592c7c5f537b8a9c63b8cb5d09ae5a6ffc7c7306e48940bcb4c7c44e ;;
detached) worker="$R/r19-root/bin/worker-final"; sha=714ef623bc198beefe0fd74ea06220ed9cc1062f428af2cabcff913362527a5b ;;
cache-prepared) worker="$N/worker-cache-prepared"; read -r sha _ < "$N/evidence/worker-cache-prepared.sha256" ;;
*) exit 1 ;;
esac
export PYTHONDONTWRITEBYTECODE=1
if [ "$size" = big ]; then
    seed="$R/r17-bounds/fixture-big"; digest=2c24c1898a8593186328dd91fff646aa0f809758d0396c9ce959fd4488d1e375
elif [ "$size" = tiny ]; then
    seed="$R/r19-bench/tiny"; digest=$(python3 "$R/r19-bench/stand/inspect_fixture.py" "$seed" | python3 -c 'import json,sys;print(json.load(sys.stdin)["archives_canonical_sha256"])')
else
    exit 1
fi
core="$R/r19-root/bin/core-stock"
wire=(); if [ "${WIRE:-yes}" = yes ]; then wire=(--wire); fi
exec python3 "$N/stand/archives.py" --source "$R/r19-root/core" --core "$core" --worker "$worker" --core-commit 048378da7cbe890d8bf8a0152e55eb28ecb5013d --core-sha256 108a024d2edad562490d1c475b38b454151cfa1398ff6f569cc27beaf9e5e208 --worker-sha256 "$sha" --reference "$R/r16-cancel/target/debug/proteus-reference-module" --golden "$seed" --expected-corpus "$digest" --case-path "$N/live-$name" --prime-core "$core" --prime-sha 108a024d2edad562490d1c475b38b454151cfa1398ff6f569cc27beaf9e5e208 --state absent --out "$N/evidence/$name" --desktop-bridge "$R/r20-desktop/desktop_api.py" "${wire[@]}"
