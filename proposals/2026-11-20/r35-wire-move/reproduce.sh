#!/usr/bin/env bash
set -euo pipefail
# Usage: bash reproduce.sh BASE_CORE_CHECKOUT CARGO_ARTIFACTS_JSONL OUT_DIR
root=$(cd "$(dirname "$0")" && pwd)
core=$(realpath "$1"); artifacts=$(realpath "$2")
out=$(realpath -m "$3"); mkdir -p "$out"
base=048378da7cbe890d8bf8a0152e55eb28ecb5013d
wire=crates/proteus-module-protocol/src/v3/wire.rs
libs=()
for name in anyhow serde_json proteus_contracts proteus_module_protocol; do
    rlib=$(python3 - "$artifacts" "$name" <<'PYCODE'
import sys, json
rows = [json.loads(line) for line in open(sys.argv[1])]
files = {f for x in rows if x.get("reason") == "compiler-artifact" and x["target"]["name"] == sys.argv[2] for f in x["filenames"] if f.endswith(".rlib")}
assert len(files) == 1, (sys.argv[2], files)
print(files.pop())
PYCODE
    )
    libs+=(--extern "$name=$rlib")
    deps=$(dirname "$rlib")
done
for variant in stock candidate; do
    dir="$out/$variant"; mkdir -p "$dir"
    git -C "$core" show "$base:$wire" > "$dir/wire.rs"
    if [[ "$variant" = candidate ]]; then patch --quiet "$dir/wire.rs" "$root/source.patch"; fi
    cp "$root/probe.rs" "$dir/main.rs"
    "${RUSTC:-rustc}" --edition=2024 -C opt-level=3 -C debuginfo=0 -L dependency="$deps" "${libs[@]}" "$dir/main.rs" -o "$dir/probe"
    "$dir/probe" "$dir/frames" > "$out/$variant.csv"
done
diff -qr "$out/stock/frames" "$out/candidate/frames"
(cd "$out/stock/frames" && sha256sum *) > "$out/exact-frame-sha256.txt"
