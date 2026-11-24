# M395 Desktop: deduplicate installed font families before copying names

One source change in `vendor/gpui-fast-wgpu/src/cosmic_text_system.rs`.
The native font database records faces, not unique family names. A family
with Regular, Italic and Bold used to allocate three strings, and the
returned vector could retain capacity for all faces even after deduplication.
The renderer now sorts borrowed first-family names, deduplicates, and
materializes only the returned names. The existing alphabetical, exact-case
order and first-name (not localized alias) rules are unchanged; no new
cache, font loading, glyph fallback, graphics driver or user setting.

This runs before the first window: the real main registers bundled Noto,
then the component theme's installed-family lookup and Desktop's own font
inventory both call the same Cosmic backend. The allocation measurement
runs these two actual name-projection methods in sequence over native pinned
fontdb, with the exact SharedString value conversion. Application and font
state holders are thin adapters; no GPU or shaping is tested.

| Host Linux fontdb + pinned bundled Noto, 472 faces / 258 families | Stock | Candidate |
| --- | ---: | ---: |
| Scoped allocator requests | 994 | 568 |
| Gross allocator-request bytes | 72,910 | 45,636 |
| Net bytes outstanding with both inventories retained | 30,722 | 18,530 |
| Capacity of the returned native family vector | 512 | 258 |

Ordered names, blank filtering, and selection inputs are identical. The five
deterministic typed cases cover empty/duplicate-heavy/mixed/all-unique
catalogues, repeated case/localized/blank/absent names, plus a separate
live add-and-remove control. The all-unique 1,024-face control retained the
same bytes and made two additional requests for the temporary reference
vectors, while gross requested bytes decreased. The read lock is held while
the borrowed list is sorted and copied; no concurrent font writer is used
in this startup path and no lock timing claim is made.

This is a small verified first-window allocation optimization, not a fix
for hybrid EGL/GLES/Vulkan mappings. The native renderer, process memory and
first frame are not measured. Source replay through #637 commutes in both
orders and restores exact bytes.

With Rust 1.95 and the official checksum-pinned directory source closure,
run `sha256sum -c SHA256SUMS` and `python3 verify.py --vendor PATH`.
For a native Linux inventory replay, add `--noto PATH` pointing to the
exact bundled font asset whose Git hash is pinned in the receipt. Host
catalogue size can differ; only the portable typed cases require identical
numeric observations across machines.
