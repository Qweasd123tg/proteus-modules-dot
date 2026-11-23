#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
r=$PWD
export PYTHONDONTWRITEBYTECODE=1
if (( $# == 0 )); then set -- carry-1 drop-1 drop-2 carry-2; fi
for arm in "$@"; do
    date -u --iso-8601=ns
    flags=()
    if [[ "$arm" == drop-* ]]; then flags=(--idle-cap 0); fi
    python3 r23/stand/run.py \
       --binary "$r/r19-root/bin/core-stock" --module "$r/r16-cancel/target/debug/proteus-reference-module" \
       --storage "$r/r19-root/bin/worker-stock" --driver "$r/r23/driver" --output "$r/r23/$arm" --counts 1 5 10 --rounds 1 \
       --interval .08 --max-pss-mib 2860 --timeout 120 "${flags[@]}"
done
