# Markdown: keep reference definitions without copying their text on render

The Markdown worker formerly cloned every stored prefix definition and every
just-parsed definition into a second table before it decided whether the
table changed. Borrow the two consecutive slices in source order instead.
Compare only the tail when the prefix was reused. An unchanged table keeps its
owned allocation; on successful rendering of a changed table, transfer the
retained prefix strings and new parsed strings into an exactly sized vector.
A failed render still never updates the stored definitions. Formatting,
first-definition precedence (including duplicates and nested definitions),
invalidations, fence IDs, proof of cache boundary, escaping and protocol stay
the same. No renderer/parse limits change; when definitions disappear the old
table and its capacity are released.

**Base:** exact Extensions M350 native archive (151 inputs, Git tree
`4b1793c116d3d10f03782e6fe71fe5146c446b99`) plus exact accepted #596/#598/#601.
One product file only: `packages/markdown-render/src/render.rs`, changes in
`source.patch`; the Rust tests in the file are byte-identical. No lock change.
Native workspace explicitly enables serde_json preserve_order; this change
does not modify JSON maps or serializer paths.

**Checks:** both exact arms passed 52 original unit + 3 original process tests
in actual Rust/Cargo 1.95.0 (locked offline). The additional real binary,
protocol-v4 process trace checks 500 definitions, late/edited/removed reference,
duplicate precedence and blockquote definitions, CRLF and UTF-8, provider
switch, still exact embedded code, and close and reopen under another session.
All eight raw responses identical: 6,195 bytes, SHA-256
`eb2727b3fa93176bc58ec7e2d75756f05c0ea9db3c6afbc1a2c50e0c3fe084c9`.

The separate scoped allocator proof runs the actual Markdown Document::render
path with 600 definitions (417,380 definition UTF-8 bytes), phase changes and
another render that releases the definitions entirely:

| Render phase | Allocation requests before → after (excl. realloc) | Total requested bytes before → after |
| --- | ---: | ---: |
| Cold | 227,065 → 226,465 | 273,170,582 → 272,753,202 |
| Warm changed prose, unchanged definitions | 693 → 92 | 447,044 → 15,264 |
| One new suffix definition | 274,702 → 274,101 | 348,545,106 → 348,098,912 |

The small warm request covers rendering after the immutable fence, not a
reparse of the input prefix. It confirms that all 600 definition data pointers
are kept both after equal definitions and after adding a suffix definition.
Totals count allocation and reallocation requests on the calling Rust thread
inside the render, not live/persistent heap, PSS/RSS, latency, or GUI startup.

**Reproduce:** with Rust/Cargo 1.95.0 and the verified 27-package locked Cargo vendor:

    python3 proof.py --baseline /path/Extensions-M350-native-inputs.tar.gz       --height /path/596/source.patch --widgets /path/598/source.patch       --mermaid /path/601/source.patch --vendor /path/vendor --work /path/scratch

Runs in a new temporary copy, verifies the patch, dependencies using the
original lock, exact forward and inverse/reversal of all 151 source inputs,
native suites, the real stdio process and differential allocation proof.
