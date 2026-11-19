#!/bin/bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
base=$(realpath "$here/../perf-r9-baseline")
pack=$(realpath "$here/../perf-r12-root/qualified-production.patch")
extra=()
for f in "$@"; do extra+=("$(realpath "$f")"); done
cd "$base/core"
p=crates/proteus-core/src
prep="$p/core/session_store/remote/prepared.rs"; probe="$p/app_server/http/tests/session_reads.rs"
rm -f "$here/prep.bak" "$here/probe.bak"
git apply --check "$pack"
git apply "$pack"
applied=()
restore() {
 if [[ -f "$here/prep.bak" ]]; then cp "$here/prep.bak" "$prep"; fi
 if [[ -f "$here/probe.bak" ]]; then cp "$here/probe.bak" "$probe"; fi
 for ((i=${#applied[@]}-1; i>=0; i--)); do git apply -R "${applied[i]}"; done
 git apply -R "$pack"
}
trap restore EXIT
for f in "${extra[@]}"; do git apply --check "$f"; git apply "$f"; applied+=("$f"); done
cp "$prep" "$here/prep.bak"; cp "$probe" "$here/probe.bak"
python3 "$here/ready_bound.py" "$PWD"
TMPDIR="$here/fixtures" bash "$base/build-core.sh" > "$here/build.log" 2>&1
bin=$(sed -n 's/^  Executable unittests .* (\(.*\))$/\1/p' "$here/build.log" | tail -1)
test -x "$bin"
cp "$bin" "$here/experiment-appserver-test"
