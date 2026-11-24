# Desktop: avoid the original-size copy for large center-crop previews

One Desktop production patch against exact M419 (Desktop tree unchanged
from M417). In a visible message attachment preview, resizing previously
made a new full-resolution square before producing the bounded thumbnail.
For sufficiently downsampled non-square RGB/RGBA8 images, a typed view of
the same centered pixels feeds the same locked image 0.25.10 Triangle
filter directly. It avoids the extra copy without changing pixel order,
color metadata, EXIF transform, animation frames or delays, BGRA layout,
thumbnail geometry, decode limits, cache and upload logic. Unqualified
images keep the old path.

The source remains alive during resizing with a view, so the fast path
requires the smaller original side to be at least 16 and at least 8×
the output edge. At that ratio the pinned filter's intermediate and
output are smaller than even the RGB8 crop. No filter reordering, new
unsafe production code, dependencies or lockfile changes.

## Scoped native A/B

Rust 1.95 release on Linux; both exact image source arms in one ELF. The
harness uses the locked PNG/JPEG/GIF/WebP decoders and interpolation
code and keeps real Frame values at a minimal GPUI RenderImage boundary.
Twenty-three native tests passed: exact BGRA pixel bytes and CICP color
metadata, odd offsets and aspect ratios, active guard boundary, color/
16-bit paths, very thin rasters, transparency, orientation, animation
frames/delays, and decode budget, invalid/oversized/overlong errors.
The real scheduler call to this entry point is source-pinned; full
GPUI scheduling, atlas or process PSS was not measured.

| Thumbnail scope: resident decoded raster and filter | Stock peak requested bytes | Candidate |
| --- | ---: | ---: |
| RGBA 6144×4096, 384 px | 167,772,160 | 126,419,072 |
| RGB 6133×4151, 384 px | 128,066,652 | 102,320,489 |
| RGB 2048×1024, 96 px | 9,437,184 | 7,892,096 |

All retained output allocations matched exactly. Thin 32768×1,
near-square at high scale, and 16-bit negative-control peaks were
exactly unchanged. The peak numbers count *requested live Rust
allocator bytes* around the input copy and filter, excluding the PNG/
JPEG codec's own allocations, atlas, system memory and PSS.

Separate unmetered CPU7 median timings from nine alternating pairs per
shape: eligible large RGBA −21.4%, large RGB −32.3%, 2048×1024
RGBA at edge 96 −14.8%. An edge-192 same-shape control used the old
path both ways and differed by −6.1%, so interpret small timing
deltas with caution; all raw pairs are included. These are filter
timings, not codec, full UI or cold 50k text-only results. The exact
Desktop manifest, source, image features and 26 dependency checksums
are pinned in the receipt. All successful build/test phases passed
both disk guards in before/min/last samples; the initial shim
compilation failed only for missing test-only comparison traits and
is not used as a passing receipt.

## Verification

```sh
sha256sum -c SHA256SUMS
python3 replay.py /path/to/exact/Desktop
python3 prepare-native.py /path/to/exact/Desktop /tmp/empty-new-proof
cd /tmp/empty-new-proof
# Exact official locked dependencies must already be in the Cargo cache/vendor.
cargo test --locked --offline --release -j 2 -- --test-threads=1 --nocapture
# Optional separate timing on an idle, allowed pinned CPU:
taskset -c 7 cargo test --locked --offline --release -- \
  --ignored paired_resize_timing_unmetered --test-threads=1 --nocapture
```
