#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
for arm in page control control page; do
    case "$arm" in
      page) count=${count_page:-1}; count_page=$((count+1)); exe=r22/display-page/worker-page-1m ;;
      control) count=${count_control:-1}; count_control=$((count+1)); exe=r19-root/bin/worker-final ;;
    esac
    date -u --iso-8601=ns
    WIRE=${WIRE:-no} bash r22/run.sh "$arm-${TAG:-pagecompare}-$count" "$exe" || echo "failed:$arm/$count"
done
date -u --iso-8601=ns
