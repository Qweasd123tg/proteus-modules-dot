# Desktop: skip redundant expanded tool-block line counts

One production hunk for [Proteus Desktop f8cc40177ad3ab3d8ec36447a899332778f03268](https://github.com/Proteus-harness/Proteus-desktop/tree/f8cc40177ad3ab3d8ec36447a899332778f03268), in `Fold::block` in `src/ui/chat/tool_row.rs`.

## Change

When the selected full flag is true, the caption is always “Свернуть”. Classify the block using the strict 2,000 UTF-8 byte threshold, then (only at or below it) look for a 13th `str::lines()` item. Do not count preview lines in this branch. A collapsed block still counts the entire source and subtracts the **trimmed preview's** actual line count for the exact existing caption. An invalid part index still falls back to collapsed. Short text still uses `trim_end`.

The preview remains eagerly formatted. The full formatter, its byte/line caps and exact suffix/truncation labels, clipboard callback, state toggles, clip surfaces and reveal code remain byte-identical. A closing inner reveal can still invoke the full formatter with its selected flag false; this patch does not change that behavior. This is a selected-full row operation, not a cold history-opening optimization.

## Verification

Using Rust 1.95.0 at optimization levels 0 and 3, the paired source lift matched 330,752 stock/candidate projections in each run, including full/collapsed and invalid part indices, UTF-8/whitespace and LF/CRLF/lone CR, both byte and line limits, trimmed preview hidden counts, exact captions, and full clipping. It copies the production classification and caption statements and both real formatters; GPUI is replaced at the rendering boundary. The lift evaluates the exact full-formatter output on every long case solely to compare output, not to simulate when real reveal code calls it.

An instrumented copy measures logical line items yielded to the classification and caption iterators, **not** formatter iterators, bytes visited, CPU time, or process memory. Exact output is also checked in the uninstrumented lift. Observed stock → candidate:

| Fixture | Source lines yielded | Preview lines yielded |
|---|---:|---:|
| Selected full, 65,536 lines | 65,536 → 0 | 12 → 0 |
| Collapsed or invalid part, 65,536 lines | 65,536 → 65,536 | 12 → 12 |
| Selected full, 2,000 bytes / 500 lines | 500 → 13 | 12 → 0 |
| Selected full, 128 KiB single line | 1 → 0 | 1 → 0 |
| Selected full, 12-line short block | 12 → 12 | 0 → 0 |

The patch applies and reverses byte-for-byte, preserves file mode, and passes rustfmt. The same proof runs with stock formatter, [#542](https://github.com/Qweasd123tg/proteus-modules-dot/pull/542), [#546](https://github.com/Qweasd123tg/proteus-modules-dot/pull/546), or both; all six three-patch apply orders and their reversals agree on all intermediate source subsets. The two previous patches are included as test fixtures, not required production changes. No native Desktop build, rendering/compositor test, latency benchmark, allocation benchmark, or peak memory measurement was performed.

## Reproduce

With the pinned Desktop sources and Rust 1.95.0 available:

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py /absolute/path/to/Desktop /absolute/path/to/rustc /absolute/path/to/rustfmt
```

The proof copies two pinned source files into temporary directories. It uses only their lifted Rust code, with no external crates or downloads. See `evidence.log` and `SOURCE-PROVENANCE.json`.
