# Finish one-span transcript edits directly into a fresh Arc

Exact base: [Proteus-desktop at f8cc4017](https://github.com/Proteus-harness/Proteus-desktop/tree/f8cc40177ad3ab3d8ec36447a899332778f03268), `src/transcript/text_run.rs`.

When a batched update ends with just retained row text or just newly supplied text, create the result directly from that one slice instead of copying it through a second `String`. The result is always a **fresh** `Arc<str>`, including empty output or text equal to the old row. The existing two-span path and the length check stay unchanged. The common singleton path, offset rules, cursor/filter logic, per-event outcomes, row identity, and routing are unchanged.

The logical test counter counts copies into the intermediate `String`, not the final Arc, so a prefix-only result now contributes zero to that counter. The accompanying source tests cover unchanged and truncated prefixes, same-text tail replacement, empty result, and a mixed control.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

[#354](https://github.com/Qweasd123tg/proteus-modules-dot/pull/354) is already included: its exact delivery artifact names the two current stock postimages. Do not reapply it.

## Verification

Use the externally pinned files from `SOURCE-PROVENANCE.json` under the listed `*.ref` names.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /path/to/private/scratch \
  --rustc /path/to/pinned/rustc
```

Both files applied and reversed byte-for-byte in private scratch and passed rustfmt. The native Rust 1.95 source lift passed 23/23 in debug and optimized modes: the actual text-run code, exact single-event assistant text arm and relevant reducer helpers, the same 387,072 UTF-8 offset/partition cases in each source arm, and the added outcome, fresh Arc and measured allocation checks. Host envelopes, entry-only fixture construction, and metadata are inert. The full Desktop app/test suite, UI, and actual service were not run.

For a 1 MiB result in each single-span fixture, scoped allocation requests inside `finish` went from 2 to 1 (2,097,168 to 1,048,592 summed requested bytes), with no reallocations. Mixed and empty controls were unchanged. Inputs and delta application were prepared before measurement; this does not measure the full reducer, memory peak, RSS/PSS, latency, or UI responsiveness.
