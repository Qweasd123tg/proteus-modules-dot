#!/usr/bin/env bash
# Linux x86_64; Rust 1.95. $1 Core git checkout, $2 Modules git checkout, $3 fresh output
# directory; optional $4 release/deps directory built at the pinned Core revision.
set -euo pipefail
core=$(cd "$1" && pwd); modules=$(cd "$2" && pwd); here=$(cd "$(dirname "$0")" && pwd)
external=''; if [[ -n "${4:-}" ]]; then external=$(cd "$4" && pwd); fi
mkdir "$3"; out=$(cd "$3" && pwd); mkdir "$out/src" "$out/modules"
git -C "$core" archive 8ea2cdaf4195ae24e941354f68d4e97335d139d7 | tar -xf - -C "$out/src"
git -C "$modules" archive 37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979 tool/file-tools/src tool/git-tools/src | tar -xf - -C "$out/modules"
python3 "$here/capture.py" "$out/modules" > "$out/tools.json"; cmp "$here/tools.json" "$out/tools.json"
cd "$out/src"; git init --quiet
if [[ -z "$external" ]]; then
    cargo build --locked --release -p proteus-contracts --target-dir "$out/target"
    deps="$out/target/release/deps"
else
    deps="$external"
fi
crate_path() {
    local paths=("$deps/lib$1-"*.rlib)
    if [[ ${#paths[@]} != 1 || ! -f ${paths[0]} ]]; then echo "Need exactly one release artifact for $1" >&2; return 1; fi
    printf '%s' "${paths[0]}"
}
ctr=$(crate_path proteus_contracts); serde=$(crate_path serde); json=$(crate_path serde_json)
src=crates/proteus-contracts/src/model_standard/canonical_response.rs
for v in base candidate; do
    if [[ $v == candidate ]]; then git apply --check "$here/compact-tool-validation.patch"; git apply "$here/compact-tool-validation.patch"; fi
    { echo 'pub use proteus_contracts::{model_standard, domain};'; echo "#[path=\"$src\"] mod validator;"; echo 'use validator::ModelResponseValidationContext;'; sed 's/, ModelResponseValidationContext}/}/' "$here/probe.rs"; } > wrap.rs
    for mode in heap time; do
        flags=(); [[ $mode != heap ]] || flags=(--cfg probe_heap)
        rustc --edition=2024 -A dead_code -A unused_imports -O "${flags[@]}" -L "dependency=$deps" --extern "proteus_contracts=$ctr" --extern "serde=$serde" --extern "serde_json=$json" wrap.rs -o "$out/$v-$mode"
    done
    "$out/$v-heap" "$out/tools.json" > "$out/$v-heap.txt"
done
for i in 1 2; do versions=(base candidate); [[ $i == 1 ]] || versions=(candidate base); for v in "${versions[@]}"; do "$out/$v-time" "$out/tools.json" > "$out/$v-time-$i.txt"; done; done
python3 "$here/summarize.py" "$out" > "$out/results.json"
