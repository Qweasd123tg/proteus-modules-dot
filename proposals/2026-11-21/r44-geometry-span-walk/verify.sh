#!/usr/bin/env bash
# Usage: bash verify.sh /path/to/Proteus-desktop /path/to/libsum_tree-<hash>.rlib
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(realpath "${1:?Desktop checkout}")
sum=$(realpath -s "${2:?compiled Desktop sum_tree rlib}")
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
cd "$w"
dir=src/ui/chat/scroller/scrollbar
git -C "$repo" archive "$base" "$dir/geometry.rs" "$dir/height_map.rs" "$dir/height_map" | tar xf -
flags=(--edition=2024 -C strip=symbols -L dependency="$(dirname "$sum")" --extern sum_tree="$sum")
# This only affects rustc's linker choice on Linux.
[[ $(uname -s) != Linux ]] || flags+=(-C link-arg=-fuse-ld=lld)
for arm in base patched; do
  if [[ $arm == patched ]]; then git apply --check "$here/source.patch"; git apply "$here/source.patch"; git apply --reverse --check "$here/source.patch"; fi
  printf '#![allow(dead_code)]\n#[path="%s/height_map.rs"] mod height_map;\n' "$dir" > test.rs
  rustc "${flags[@]}" --test test.rs -o tests
  ./tests --test-threads=1
  cp "$here/probe.rs" probe.rs
  python3 - "$dir/geometry.rs" <<'PY'
from pathlib import Path
import sys
s = Path(sys.argv[1]).read_text().split("    fn rebuild(&mut self) {", 1)[1]
a = s.index("                self.prefix.clear();")
b = s.index("                self.before = ", a)
Path("kernel.rs").write_text("{\n" + s[a:b] + "}\n")
PY
  rustc "${flags[@]}" -C opt-level=3 probe.rs -o "probe-$arm"
done
for n in 1 2 3 4 5 6; do
  if (( n % 2 )); then arms=(base patched); else arms=(patched base); fi
  for arm in "${arms[@]}"; do ./"probe-$arm" >> "$arm.tsv"; done
done
python3 - <<'PY'
from collections import defaultdict
from statistics import median
def read(arm):
    d=defaultdict(list)
    for line in open(arm+".tsv"):
        case, checksum, ns = line.split()
        d[case,checksum].append(float(ns))
    return d
a,b=read("base"),read("patched")
assert a.keys()==b.keys() and all(len(v)==6 for m in (a,b) for v in m.values())
print("scenario hash median_base_ns median_patched_ns")
for k in a:
    print(*k, f"{median(a[k]):.2f}", f"{median(b[k]):.2f}")
PY
