# Analysis: skip the second copy of disclosure text

Standalone production patch for [Proteus-desktop-extensions at `923077d3`](https://github.com/Proteus-harness/Proteus-desktop-extensions/tree/923077d3967ae7063a6556bc378c09f97abc2854). The only changed path is `packages/analysis/src/nodes.rs`; the SDK, package manifests, and lockfile are unchanged. [Dot #570](https://github.com/Qweasd123tg/proteus-modules-dot/pull/570) is optional, not installed upstream and not a prerequisite.

The Analysis disclosure helper previously made the full text owned, then passed the code widget to SDK `ui::disclosure`, whose `json!` serialization copied the widget and its full text again. Let that same SDK build the same widget with a placeholder in the existing text field, then fill that field in place. Borrowed text is copied once. Move a pretty-printed string only if its capacity is already tight; otherwise make the same tight copy as stock. Widget shape, field order, escaping, height, wrap, initial disclosure state and output capacity are unchanged.

## Results

- Authentic Rust and Cargo 1.95.0: all 19 original `extension-analysis` tests passed separately in clean stock, standalone candidate and an optional composition with the exact #570 patch. Four optimized release proof tests passed on stock and five each on candidate and composition, including two exact stock height tests in each.
- The actual native `turn_summary` and `step_card` entry points emitted byte-identical serialized widgets across all three builds. Fixtures contain synthetic final-answer and tool-result strings over 1 MiB each, plus ordered JSON, Unicode, CRLF, NUL, quotes, and initially open and closed fields. The paired helper tests also check literal field order, exact capacity, borrowed-input preservation, wrapping, saturation, empty text and JSON scalars.
- The optimized helper-only meter observes **one fewer allocation request and 1,200,011 fewer requested bytes** for the 1,200,011-byte borrowed fixture (37 → 36 allocations, three reallocations in both, 2,403,609 → 1,203,598 requested bytes). A 128-byte exact-capacity pretty fixture also saves one allocation and 128 bytes. Both short and 800,000-character loose pretty controls have identical allocation/reallocation counts and requested bytes.
- These counts are cumulative bytes requested from the Rust allocator during the helper only, not live/peak heap, RSS/PSS, release binary size or latency. Other wrappers may still copy large text later. No full workspace suite, Desktop/GUI, shipping bundle or production/session data was measured.

## Reproduce

Use a clean checkout at the pin and the official Rust 1.95.0 toolchain, with its rustfmt component. `SOURCE-PROVENANCE.json` also inventories the 151 verified workspace source entries if reconstructing them locally; preserve the license symlinks. The dependency directory must contain `archives/` with the 27 crates.io archives from the original lock and the corresponding Cargo directory source under `vendor/` (package directories with `.cargo-checksum.json`). The proof checks archive hashes against the original lock and checks every vendor file against its archived bytes. Use Python 3.11+ and Git.

```sh
python3 -B proof.py \
  --src /path/to/pinned/extensions \
  --deps /path/to/verified/dependencies \
  --toolchain /path/to/rust-1.95/bin \
  --work /path/to/independent/writable/scratch
```

To additionally test the already checked composition, supply `--compose-rich-text /path/to/exact/570/source.patch`. The proof rejects a substituted #570 patch. All cases compile offline in separate Cargo targets from copies of the original locked workspace. Generated test modules and synthetic snapshots stay in scratch; only `source.patch` is the production change. To apply it directly, use `git apply --check source.patch` followed by `git apply source.patch` from the pinned Extensions checkout.
