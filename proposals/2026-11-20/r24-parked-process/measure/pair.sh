#!/usr/bin/env bash
# Standalone given four binaries; evidence paths are never reused.
set -euo pipefail
if [[ $# != 7 ]]; then
  echo "Usage: bash pair.sh DRIVER CORE REFERENCE STORAGE NEW_OUTPUT {1|5|10} {pilot|abba}" >&2
  exit 2
fi
here=$(cd -- "$(dirname -- "$0")" && pwd)
driver=$1; core=$2; reference=$3; storage=$4; output=$5; n=$6; plan=$7
[[ "$n" =~ ^(1|5|10)$ ]] || { echo 'unsupported peer count' >&2; exit 2; }
case "$plan" in
  pilot) [[ $n == 1 ]] || { echo 'pilot must have one peer' >&2; exit 2; }; arm_order=(park retain) ;;
  abba) arm_order=(retain park park retain) ;;
  *) echo 'unsupported plan' >&2; exit 2 ;;
esac
mkdir -- "$output"
export PYTHONDONTWRITEBYTECODE=1
arms=()
i=0
for strategy in "${arm_order[@]}"; do
  dir="$output/$i-$strategy"
  flags=()
  if [[ "$strategy" == park ]]; then flags=(--idle-cap 0); fi
  # Four KiB keeps second-turn history bounded; not an R23 32KiB latency comparison.
  python3 "$here/run.py" --driver "$driver" --binary "$core" --module "$reference" --storage "$storage" \
    --output "$dir" --counts "$n" --rounds 2 --payload-kib 4 --delay-ms 500 --interval .08 \
    --timeout 120 --max-pss-mib 512 "${flags[@]}"
  arms+=("$dir")
  i=$((i+1))
done
python3 "$here/compare.py" "${arms[@]}" > "$output/comparison.json"
