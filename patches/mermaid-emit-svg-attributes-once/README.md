# Mermaid: emit final escaped SVG attribute fragments directly

`source.patch` changes only `packages/mermaid-render/svg-theme.mjs` in
`Proteus-harness/Proteus-desktop-extensions` at
`f3adb160083161a2e5db1ee720160c04cd1d212e`.

`materializeSvg` saves the finished escaped attribute strings in one output
array, rather than returning a temporary wrapper and a key/value pair for each
attribute and mapping those pairs again. Attribute order, repeated `style`
positions, replaced-attribute suppression, the final override Map order and
escaping are unchanged. The parser, variable scopes, failure checks, SVG and
source limits, worker protocol, and permissions are not modified.

Verified on the exact installed-source Pele 1.12.0 bundle and existing Node
package tests, in four lanes: stock and patched, each with and without the
separate #475 stdin change. Each package suite passed **12/12**. The focused
proof also checked **5 exact SVG fixtures**, **8 exact defensive errors**,
**10 real Pele renders** across two themes, and **15 byte-identical JSONL
replies** in all four lanes. The explicit SVG controls cover repeated style
and ordinary attributes, override slot order, aliases, sibling inheritance,
untouched label text, entities, and a suppressed unresolved attribute.

On one 76-node Cyrillic flowchart, the exact real materialized SVG was
**47,317 bytes**. An isolated trace of the two source bodies recorded the same
674 opening tags, 1,963 ordinary attribute visits and 1,964 final fragments.
At that output seam it removes the 1,963 old `flatMap` wrapper results and
1,887 ordinary output pairs; override Map traversal and final strings remain.
These are source-level operations, not measured allocator requests, resident
memory or timings. The exact proof and scope are recorded in `verification.json`.

To rerun the existing real-vendor suite using a local exact checkout:

```sh
sha256sum -c SHA256SUMS
patch --dry-run --fuzz=0 -p1 -d "$EXTENSIONS" < source.patch
patch --fuzz=0 -p1 -d "$EXTENSIONS" < source.patch
(cd "$EXTENSIONS" && TZ=UTC LANG=C node --test packages/mermaid-render/tests/worker.test.mjs)
```

Apply the patch in a disposable checkout. #199's inherited variable sharing is
already in the source and is preserved. #475 changes `worker.mjs` only; it is
optional. No Cargo build, install, live service, or release publication.
