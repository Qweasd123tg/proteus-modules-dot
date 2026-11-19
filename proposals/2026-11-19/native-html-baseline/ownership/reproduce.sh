#!/usr/bin/env bash
# Parameters: local Proteus-desktop checkout with the pin and a new directory
set -euo pipefail
repo=${1:?desktop}; out=${2:?fresh output dir}; root=$(cd "$(dirname "$0")" && pwd); pin=210cc9f274ffe40533b390a0d9e940f251a9fa22; path=vendor/gpui-base/src/text
mkdir "$out"; out=$(cd "$out" && pwd)
git -C "$repo" show "$pin:$path/node.rs" > "$out/node.rs"
sed -n '112,153p' "$out/node.rs" > "$out/block_state.rs"
BLOCK_STATE_SOURCE="$out/block_state.rs" rustc --edition 2024 -Awarnings "$root/selection.rs" -o "$out/selection"
"$out/selection"
mkdir "$out/src"; cp "$root/fragment.rs" "$out/src/main.rs"
git -C "$repo" show "$pin:$path/format/html5minify/mod.rs" > "$out/src/stock.rs"
printf '%s\n' '[package]' 'name="fragment-probe"' 'version="0.1.0"' 'edition="2024"' '[dependencies]' 'html5ever = "=0.27.0"' 'markup5ever_rcdom = "=0.3.0"' > "$out/Cargo.toml"
cp "$root/Cargo.lock" "$out/Cargo.lock"
(cd "$out"; cargo run --locked --quiet)
