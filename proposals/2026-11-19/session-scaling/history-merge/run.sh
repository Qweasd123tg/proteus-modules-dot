#!/bin/bash
set -eu
p=$(cd "$(dirname "$0")" && pwd)
ord=(base after after base after base base after)
for v in base after; do "$p/$v/test" --test-threads=1 >"$p/$v/tests.txt"; tail -3 "$p/$v/tests.txt"; "$p/$v/alloc" >"$p/$v/alloc.csv"; done
i=0; j=0
for v in "${ord[@]}"; do if [ "$v" = base ]; then ((i+=1)); n=$i; else ((j+=1)); n=$j; fi; taskset -c "${BENCH_CPU:-2}" "$p/$v/bench" > "$p/$v/times-$n.csv"; done
