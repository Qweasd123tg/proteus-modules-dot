#!/bin/sh
set -eu
here=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$here"
# Alternate order; independent allocation counting binaries do not time latency.
for run in 1 2 3 4 5; do
    if test $((run % 2)) -eq 1; then modes="base after"; else modes="after base"; fi
    for n in 32 128 512 2048 4096; do
        for mode in $modes; do
            printf 'time %s %s ' "$run" "$mode"
            "./$mode/probe" "$n" 720 1
        done
    done
done
for n in 32 128 512 2048 4096; do
    for mode in base after; do
        printf 'alloc 1 %s ' "$mode"
        "./$mode/probe-alloc" "$n" 720 1
    done
done
