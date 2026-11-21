#!/usr/bin/env bash
# Usage: bash typecheck.sh repo sum_tree.rlib gpui_kit.rlib sha2.rlib libc.rlib async_channel.rlib uuid.rlib
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(realpath "${1:?Desktop checkout}"); shift
(( $# == 6 ))
depdir=$(cd "$(dirname "$1")" && pwd)
names=(sum_tree gpui_kit sha2 libc async_channel uuid)
flags=(-L dependency="$depdir")
for name in "${names[@]}"; do flags+=(--extern "$name=$(realpath -s "$1")"); shift; done
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"; export CARGO_MANIFEST_DIR=$w
d=src/ui/chat/scroller/scrollbar
git -C "$repo" archive "$base" "$d" src/ui/chat/scroller/scrollbar.rs | tar xf -
python3 - <<'PY'
from pathlib import Path as P
here=P.cwd()
d=here/"src/ui/chat/scroller/scrollbar"
s=d.with_suffix(".rs").read_text()
a=s.index("const UNKNOWN_ROW_HEIGHT:")
b=s.index("#[derive(Clone, Copy, Default)]\nstruct State",a)
mods="".join(f'#[path="{d/f}"] mod {f[:-3]};\n' for f in ("geometry.rs","height_cache.rs","height_map.rs","height_store.rs"))
P("harness.rs").write_text('#![allow(dead_code)]\nconst APP_ID:&str="dev.proteus.geometry-test";\nmod ui { mod chat { mod scrollbar {\n'+mods+'use height_store::Key as HeightCacheKey;use gpui_kit::{Pixels,px};\n'+s[a:b]+'}}}\n')
PY
for arm in base patched; do
  if [[ $arm == patched ]]; then git apply --check "$here/source.patch"; git apply "$here/source.patch"; fi
  rustc --edition=2024 --test -C debug-assertions=no --emit=metadata "${flags[@]}" harness.rs -o check.rmeta
  echo "PASS actual geometry, map, cache, persistence and their tests typechecked: $arm"
done
