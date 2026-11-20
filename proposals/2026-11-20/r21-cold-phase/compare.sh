#!/bin/bash
# Compare in reverse order of the earlier instrumented stock observation.
set -euo pipefail
cd "$(dirname "$0")/.."
R=$PWD; N=$R/r21-cold
test -x "$N/worker-cache-prepared"
(
 cd "$N"
 sha256sum worker-cache-prepared > evidence/worker-cache-prepared.sha256
 git -C modules rev-parse HEAD HEAD^ HEAD^{tree}
 git -C modules diff --exit-code
 git -C modules diff --cached --exit-code
 cat evidence/worker-cache-prepared.sha256
) > "$N/evidence/cache-source-receipt.log"
date -u --iso-8601=ns
bash "$N/run.sh" cache-prepared cache-prepared-timing
date -u --iso-8601=ns
bash "$N/run.sh" stock cache-stock-timing
date -u --iso-8601=ns
python3 "$N/summarize.py" "$N/evidence/stock-125k" "$N/evidence/cache-prepared-timing" "$N/evidence/cache-stock-timing" > "$N/evidence/cache-comparison.json"
