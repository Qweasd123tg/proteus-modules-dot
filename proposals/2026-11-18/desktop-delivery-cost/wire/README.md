# Desktop / Extensions integration: official fixture and renderer-only memory

Compared pinned Proteus-desktop `210cc9f274ffe40533b390a0d9e940f251a9fa22`, with its [declared Extensions pin](https://github.com/Proteus-harness/Proteus-desktop/blob/210cc9f274ffe40533b390a0d9e940f251a9fa22/repositories.json) `a35cea08be83ee8e5ecbfce9ef5050a1c00eb247`. Both were also the heads of their respective main branches when checked. The only changed tracked extension path is `packages/markdown-render/src/plain.rs` from the previous plain-link proposal. No upstream source was changed.

## Official producer, not a rendered window

[The Desktop test wrapper](https://github.com/Proteus-harness/Proteus-desktop/blob/210cc9f274ffe40533b390a0d9e940f251a9fa22/scripts/test.py) calls Extensions’ `package.py --dev` for `--build-extensions` and checks each manifest executable. This step completed on both sides, with separate source and build directories and no binary copied from one side to the other. `rustc`/Cargo 1.95.0; locked Extension dependency archives matched their SHA-256s. Of 14 independently built executables, the other 13 were byte-identical; only the renderer differed. All 1,459 Desktop tracked entries matched its GitHub tree, including file modes. The pristine Extensions tree hash matched upstream; 467 tracked entries checked in both staged trees. See [source and ELF hashes](sources.json).

The [official Desktop conformance test](https://github.com/Proteus-harness/Proteus-desktop/blob/210cc9f274ffe40533b390a0d9e940f251a9fa22/src/declarative/protocol.rs) launches [the stock Extensions producer](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/a35cea08be83ee8e5ecbfce9ef5050a1c00eb247/tests/wire.py), then uses Desktop’s Rust manifest discovery, typed parser and widget visitor. **The unchanged Python producer ran against each complete 14-package installation:** 173 messages, 335,757 bytes on each side, byte-for-byte equal, SHA-256 `0b4f227a307137a6fe43e0ecc85b8a17a9c454bf84c337c6ca3a953155a0848b`. Included 123 view frames, 34 badge frames, and one expected content_error, among others. Uses the fixture’s synthetic loopback API, temporary configs and local workers. The stock fixture renders Markdown, not the specific 53 KiB plain-text input; those are separate tests. [Counts and checksums](stock-wire.json).

**Native gate status.** The *verbatim body* of Desktop's `shipped_processes_conform_to_the_public_ui_protocol` was additionally executed in a source-bound, no-window Rust binary on both roots. Both passed: real manifest discovery (14 packages, zero errors), fresh untouched Python wire producer, real typed parse/validation and node visitor, no Unknown widgets, frame-count gate. A second replay of each captured stream recognised every View across all 173 frames. Headless glue substitutes pinned Lucide asset-name membership for the drawing enum and omits unused visual preferences access. **This is not the stock native test binary**: the official `cargo test … --ignored --exact` under the Desktop wrapper was attempted on both sides, but its dependency `yeslogic-fontconfig-sys 6.0.1` failed (exit 101) because pkg-config could not locate the system's `fontconfig.pc`. Native compilation did not complete. [Status and exact boundary](gate-status.json). No app window, compositor presentation, live model or user data was involved.

## Separate renderer proportional set size (PSS)

Linux /proc/PID/smaps_rollup of the **actual markdown-render child**; its PID’s executable was verified against its own package. Eight fresh process pairs per condition in alternating order, one short warmup and eight 53 KiB messages per child, same source/changes/returned views. Sampled roughly every 1 ms plus at each reply. No timing claim from the sampled process, no parent memory included. Figures are medians across processes in KiB:

| Input | Sampled maximum, before → after | Immediately after eight replies |
|---|---:|---:|
| 53,762 bytes, no URL | **5,849 → 2,071** | **4,207 → 2,071** |
| 53,784 bytes, URL at end | 5,853 → 5,987 | 4,247 → 4,251 |

Above the individual warmup level the median difference to the sampled maximum on no-URL text was 4,036 → 508 KiB. All output digests matched; the URL cases actually emitted a link rather than losing it. The renderer still runs the original parser when the delimiter is present, so no URL-case memory saving is claimed. These are **sampled maxima, not the kernel’s peak PSS**, system memory, GUI process-tree memory, layout or presentation time. [Raw samples](renderer-pss.json) · [driver](renderer_pss.py).

## Reproduce

Use a clean pinned Desktop and two independent pinned Extensions checkouts. Apply only the plain-link fast-path patch in the second. For each side, from the Desktop checkout:

```sh
export PROTEUS_EXTENSIONS_SOURCE=/path/to/that/extensions
export CARGO_TARGET_DIR=/separate/build/target-for-that-side
python3 scripts/test.py --build-extensions --no-default-features --release -p proteus-native --bin proteus-native \
  declarative::protocol::tests::shipped_processes_conform_to_the_public_ui_protocol -- --ignored --exact
python3 "$PROTEUS_EXTENSIONS_SOURCE/tests/wire.py" --wire > /path/to/that-side.jsonl
```

The explicit libtest filter is important: the ignored native test is not part of a random passing package run. `--no-default-features` skips the unrelated native Ghostty build, not GPUI dependencies. On a complete Desktop build host remove it to use the default terminal engine. To reproduce the stock producer without the Desktop SDK, first run `python3 package.py --dev` in each Extensions checkout. To reproduce renderer-only PSS on Linux: `python3 renderer_pss.py /path/to/before/extensions /path/to/after/extensions`.
