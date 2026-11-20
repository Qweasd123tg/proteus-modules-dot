#!/bin/bash
# Exact original detached controls interleaved with one-knob, compact, and combined candidates.
set -euo pipefail
cd "$(dirname "$0")/.."
test -x r22/memory/core-compact
test -x r22/display-page/worker-page-1m
for arm in page compact combined control control combined compact page; do
  core=r19-root/bin/core-stock
  worker=r19-root/bin/worker-final
  case "$arm" in
    page) count=${count_page:-1}; count_page=$((count+1)); worker=r22/display-page/worker-page-1m ;;
    compact) count=${count_compact:-1}; count_compact=$((count+1)); core=r22/memory/core-compact ;;
    combined) count=${count_combined:-1}; count_combined=$((count+1)); core=r22/memory/core-compact; worker=r22/display-page/worker-page-1m ;;
    control) count=${count_control:-1}; count_control=$((count+1)) ;;
  esac
  date -u --iso-8601=ns
  WIRE=no CORE_BIN="$core" bash r22/run.sh "$arm-rank-$count" "$worker" || echo "failed:$arm-rank-$count"
done
date -u --iso-8601=ns
