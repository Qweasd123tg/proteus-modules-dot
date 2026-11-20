#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
r=$PWD
exec env PYTHONDONTWRITEBYTECODE=1 python3 r23/stand/run.py \
  --binary "$r/r19-root/bin/core-stock" --module "$r/r16-cancel/target/debug/proteus-reference-module" \
  --storage "$r/r19-root/bin/worker-stock" --driver "$r/r23/driver" --output "$r/r23/resume" \
  --counts 10 --rounds 2 --interval .08 --max-pss-mib 2860 --timeout 120
