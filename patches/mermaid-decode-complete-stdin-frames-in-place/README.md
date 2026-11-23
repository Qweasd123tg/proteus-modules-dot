# Mermaid worker: decode complete stdin lines without copying them

Applies to `Proteus-harness/Proteus-desktop-extensions` at
`892f627570369ed60d7205eb0d351c753ec4305f`. `source.patch` changes only
`packages/mermaid-render/worker.mjs`.

When the current stdin Buffer contains an entire LF-terminated frame, decode
that range directly after the existing size check. A frame with pending bytes
still uses the same owned concatenation before UTF-8 decoding. An empty tail
no longer calls `Buffer.concat`. The 512 KiB limit still counts all bytes before
LF, including CR. Recovery from a bad JSON line, incomplete EOF, and fatal
oversize remain unchanged. Renderer inputs, options, theme and SVG controls,
worker lifecycle, and the package/permissions are unchanged.

Verified the real shipped Node worker with the exact in-tree Pele 1.12.0 bundle:

- Existing package Node suite: **12/12** on stock and **12/12** after the patch.
- **11 paired stdin cases**: identical raw stdout bytes, stderr, and exit status.
  Cases cover a 3733-byte complete Unicode frame, coalescing, blank and malformed
  JSON, a split UTF-8 code point, an empty chunk, LF in a separate chunk, exact
  LF/CRLF byte caps, oversize and incomplete EOF. `wire.jsonl` records the
  synthetic layouts, the actual checked outcomes, and digest of equal output.
- Forward and reverse dry-run, no fuzz, and post-apply byte readback.

The standalone harness starts the actual worker with the Rust launcher's Node
flags plus a **test-only** preload that supplies fixed stdin-chunk boundaries.
It does not replace Pele or the `renderDiagram`/`reply` functions. The existing
suite separately exercises real pipes without the preload. No Rust build,
desktop actions, external service, timing, allocator instrumentation, or RSS/PSS
measurement. The removed Buffer copy is a source-level claim, not a latency claim.

## Reproduce with local exact checkouts

Use two fresh copies of the pinned tree. From this packet directory:

```sh
sha256sum -c SHA256SUMS
patch --fuzz=0 -p1 -d "$CANDIDATE" < source.patch
(cd "$STOCK" && TZ=UTC LANG=C node --test packages/mermaid-render/tests/worker.test.mjs)
(cd "$CANDIDATE" && TZ=UTC LANG=C node --test packages/mermaid-render/tests/worker.test.mjs)
TZ=UTC LANG=C node wire-proof.mjs \
  "$STOCK/packages/mermaid-render/worker.mjs" \
  "$CANDIDATE/packages/mermaid-render/worker.mjs"
```

The Mermaid delivery overlays reviewed through #474 do not change this JS
file: #313 changes the Rust request path/Cargo files, #412 changes Rust SVG
handoff, and #474 is Modules compaction. Node proof used the exact stock file
and the patched file, not a claim of full cumulative Rust verification.
