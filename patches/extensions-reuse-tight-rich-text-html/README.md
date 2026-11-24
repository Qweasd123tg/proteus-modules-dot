# Reuse tight owned HTML in the Extensions SDK

Base: [Proteus-desktop-extensions 923077d3](https://github.com/Proteus-harness/Proteus-desktop-extensions/tree/923077d3967ae7063a6556bc378c09f97abc2854), only `sdk/src/ui.rs::rich_text`. The previous real serde macro copied every nonempty HTML payload into a new String. Reuse the caller's owned String if it is already at exact capacity; otherwise make the same tight copy as before. Then fill the existing `html` field with a borrowed lookup so field creation, order `type,id,html` and serialization remain the same. The signature and single conversion are unchanged. This does not retain spare caller capacity or touch Markdown policy, `ui::content` or Host.

> Provenance and tests apply to the patch in this packet, not a change already in Extensions upstream.

## Results

- In an optimized native SDK test, with real serde_json 1.0.152 and `preserve_order`, a prebuilt 1,200,000-byte tight String removes one request (8 → 7) and 1,200,000 requested bytes (1,200,387 → 387) inside the helper. The output retains its original pointer. An 8-byte tight input removes one 8-byte request; loose and empty controls are unchanged. These are cumulative requested Rust allocation bytes in a helper-only scope, not live heap, RSS/PSS, product memory, or timing.
- Native SDK proof: 10 passed (7 existing tests from the exact stock UI module, 3 paired checks). The paired checks cover literal key order, exact serialized bytes, NUL/CRLF, escapes, entities, Cyrillic and emoji; owned, borrowed, and custom single-conversion input; retained capacity; and scoped allocation requests.
- Native Markdown proof: 13 passed (12 exact inline tests and 1 new check). The locked Markdown compiler produced 142 tight HTML bytes for the synthetic math-free document. The SDK reused that input and serialized the same widget as the exact production inline caller. The three existing Markdown subprocess/NDJSON tests also passed both workspace runs.
- The **complete native Cargo workspace** was run for stock and candidate, offline with the original lock. Both returned 343 passed and 1 failed. The same unrelated Mermaid lifecycle test at `packages/mermaid-render/tests/wire.rs:155` expected one PID from `/proc/PID/task/TID/children`; this environment did not expose that file even for a diagnostic subprocess. The SDK's 71 and Markdown's 52 unit + 3 subprocess tests passed in both runs. No Python/experimental workspace suite, shipping bundle, Desktop/GUI or production measurements were run.

## Reproduce

Use a clean exact checkout or reconstruct the verified workspace inputs in `SOURCE-PROVENANCE.json`, preserving license symlinks. Native Cargo still uses the original lock, not a reduced proof lock. Obtain the 27 official crate archives listed in the lock into `DEPS/archives`; use their unpacked Cargo directory-source directories and verified `.cargo-checksum.json` under `DEPS/vendor`. The proof rechecks the archives against the pinned lock and verifies every extracted file against the archived bytes. Use Rust/Cargo/rustfmt 1.95.0 and Node 20 or later on PATH for the existing Mermaid tests.

```sh
python3 -B proof.py --src /path/to/pinned/extensions --deps /path/to/DEPS \
  --toolchain /path/to/rust-1.95/bin --work /path/to/writable/scratch
```

The proof compiles stock and candidate in a private scratch copy; checks exact application, reversal, formatting and the unchanged native lock; then installs only proof-local tests. It accepts two identical native outcomes: a full pass, or the one documented scratch-environment procfs failure when the required file is absent. To apply only the production change, use `git apply --check source.patch` then `git apply source.patch` from the pinned checkout.
