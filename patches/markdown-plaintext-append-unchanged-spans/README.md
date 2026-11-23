# Markdown plaintext: append unchanged spans in bulk

Source: [Proteus-desktop-extensions at 923077d](https://github.com/Proteus-harness/Proteus-desktop-extensions/tree/923077d3967ae7063a6556bc378c09f97abc2854), `packages/markdown-render/src/plain.rs`.

Ordinary `text/plain` content passes through this escape helper. Instead of appending each unchanged character separately, scan the input bytes and append one nonempty borrowed slice between adjacent escapes. Only the same four ASCII bytes (&, <, > and double quote) interrupt a span. They cannot occur inside a multibyte UTF-8 character, so every slice endpoint is a character boundary. The four replacement strings, authored whitespace, control characters, text bytes, accepted URL spans, HTML wrapper and link markup stay identical. No change to Markdown parsing, URL recognition, UI calls, tool/provider behavior or dependencies. Highlight of scope: this is the plaintext branch, not ordinary Markdown or the preview demo.

On the exact Extensions revision:

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

The raw patch can be applied before or after the exact [#544 delivery artifact](https://github.com/Qweasd123tg/proteus-modules-dot/pull/544) at head `a37e78e49582658a837e4e22afe71e5ebf717bc7`. The two hunks edit different functions. Both application orders converge to Git blob `739634ee4ffb0c5998c2669e8b15352bb285c637`; reversing respectively restores the exact input. Tested both orders and both reverse orders with unmodified patches and no context dropping in a private synthetic tree.

## Verification

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --stock /path/to/pinned/plain.rs \
  --prior /path/to/544/source.patch --dispatch /path/to/pinned/main.rs \
  --rustc /path/to/pinned/rustc --work /path/to/private/workdir
```

The proof authenticates all source inputs, replays the exact patches both ways, and compiles the actual escape, link-filtering and render bodies from all four variants. It supplies an inert Markdown parser with fixture offsets and an inert UI reply. Rust 1.95 passed 8/8 tests in both debug and optimized modes: all 1,112,064 Unicode scalar values, 4,096 generated cases comparing all four variants for escaped and rendered output, fixed control/whitespace/entity cases, Unicode URL link and label boundaries, and parser error propagation. The native package tests are unchanged but were not run. No actual Markdown parser, UI serialization, Cargo integration, system launch or performance benchmark was used.

An instrumented copy of the exact escape body confirms mutating append calls go from 131,072 to 1 for a 128 KiB unchanged ASCII fixture, and from 98,306 to 5 for three 32,768-scalar mixed UTF-8 spans separated by two escapes. A dense four-entity fixture still calls the appender exactly four times; empty input does not append. These are structural counts, not time, allocation, memory or general speed claims. Multibyte spans are scanned by bytes, not scalars, and the final HTML byte length is unchanged.
