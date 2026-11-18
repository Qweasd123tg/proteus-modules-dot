#!/usr/bin/env bash
# Usage: bash reproduce.sh /path/to/Proteus-modules /new/output-directory [--cpu 3]
# Needs Rust/Cargo from rust-toolchain.toml, lld, Python 3, and pinned crates.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$1" && pwd)
out=$(mkdir -p "$2" && cd "$2" && pwd)
shift 2
temp=$(mktemp -d)
pin=37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979
target=workflow/coding-workflow/src/tests/dynamic_tool_surface.rs
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$temp/target}"
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}"
for arm in base after; do
  git clone --quiet --local --no-checkout "$repo" "$temp/$arm"
  (
    cd "$temp/$arm"
    git checkout --quiet --detach "$pin"
    if [[ "$arm" = after ]]; then
      git apply --check --whitespace=error "$here/deferred-parse.patch"
      git apply --whitespace=error "$here/deferred-parse.patch"
    fi
    cat "$here/probe.rs" >> "$target"
    touch "$target" workflow/coding-workflow/src/dynamic_tools.rs
    cargo test --locked --release -p coding-workflow --lib --no-run --message-format=json > "$temp/$arm.json"
    bin=$(python3 -c 'import json,sys; print(next(a["executable"] for l in open(sys.argv[1]) if (a:=json.loads(l)).get("executable")))' "$temp/$arm.json")
    cp "$bin" "$temp/$arm.bin"
    python3 scripts/test.py -p coding-workflow --lib --release > "$out/tests-$arm.txt"
  )
done
if cmp -s "$temp/base.bin" "$temp/after.bin"; then
  echo "The two binaries are identical; check the Cargo build environment." >&2
  exit 1
fi
python3 "$here/measure.py" "$temp/base.bin" "$temp/after.bin" "$out" "$@"
