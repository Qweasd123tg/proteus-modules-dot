# Modules: move text into the worker display reply

The pinned SDK intentionally accepts a generic JSON Value from each export.
Previously, a successful `OpenDisplaySnapshot` serialized a fully owned
display DTO to that Value while the DTO still owned a second copy of all its
visible text. The worker now adapts only negotiated `open_display_snapshot`
results: it consumes message parts and moves owned Text strings into the
corresponding fields of the Value. Serde still emits every key and its relative
position. Non-text parts and arbitrary metadata use the original serialization.
This is not a raw-frame path: the SDK still owns authority, lineage,
callbacks, cancellation, errors, frame counting and transport.

The standard pinned `SessionStorageExport` still provides the manifest,
checks initialization, and handles every other operation and unnegotiated
request. The selected request has the same typed parse and validation. The
same `StorageService` handles durable reads, cursor ownership, projections and
size limits for both branches. No SDK or protocol change, no lockfile change,
and no change to persisted data, module rights or frame admission semantics.

**Exact source:** full Modules M372 Git tree
`496938d1d62f1f0c22e98da944f301b6ae70fcf8`, 609 files; archive SHA-256
`9201c43305cde027d19aae769b1a548c0fc0a9139ecdb24c19678d65d28e4c8b`.
It matches M368 plus exact #612, byte for byte and mode for mode. The SDK is
the unchanged pinned revision `0c1b7572313230e5d123e95c722e1258a2e9ecd6`.
Strict inverse replay independently returned to the baseline; product
post-tree `6f0ea35d5761c8726606f95dbe49dfe9aba48331`.

**Actual worker tests.** Separate before/after worker processes, both JSONL
and SQLite, both serde_json default and preserve_order. On one immutable
no-model corpus each emits a 32,689,769-byte projected reply containing
all 50,000 records. Exactly the fresh random snapshot UUID is normalized;
all other wire bytes still match within each layout. Both layouts also
match the delegated display page, above-cap null projection, negotiation
denial, malformed-request error and method-authority error. For the exact
50k JSONL frame, the same full reply succeeds at its configured transport
limit; one byte below rejects with the unchanged error and writes no bytes
of the rejected frame. Both existing worker commit/ACK/restart tests pass
per arm/layout. A separate exact-value/wire serializer check covers escaped
Unicode, empty text, mixed/non-text parts and nested metadata.

**Conversion heap evidence.** The same old serde conversion and new helper
were measured over both a captured real worker reply and the actual typed
DTO returned by `StorageService` on that corpus (same measurements). In
each map layout, zero → 50,000 original text buffers are reused, and
19,688,894 copied UTF-8 bytes and 50,000 allocation/reallocation calls
are avoided. The meter begins after the DTO already exists and ends when
the JSON Value has been built:

| Native conversion | Requested heap bytes | Peak net live heap bytes above conversion entry |
|---|---:|---:|
| Default, before → after | 157,895,247 → 138,206,353 | 157,895,247 → 130,206,192 |
| preserve_order, before → after | 137,892,735 → 118,203,841 | 137,892,735 → 108,203,720 |

Counts are conversion-local allocator measurements. They do not include
other stages, filesystem work or the much broader product peak, and are
not RSS/PSS or latency claims. The Value tree still exists and is still
budget-checked and serialized by the unchanged SDK.

**Reproduce.** Only `source.patch` belongs in the product tree. Exact
historical source and verified cargo vendor preflight:

    python3 proof.py --modules /path/to/Modules-M372-source.tar.gz \
      --core /path/to/pinned-Core.tar.gz --vendor /path/to/vendor \
      --work /path/to/new-work --target /path/to/new-target --prepare-only

For the full proof, omit `--prepare-only`, provide Rust 1.95.0 and pass
`--manifest /path/to/fixtures.json` for the shared synthetic durable corpus
(JSONL and SQLite, 50,000 no-model rows, 4/5 text repeats); it is the corpus
seeded by the staged-display service proof in #608. The manifest points to
local test journals and is not distributed as product data. The verifier
rebuilds both worker arms on the same old SDK, runs existing process tests,
then runs paired exact-frame and conversion checks. The captured candidate
was freshly linked from verified SDK/storage dependency artifacts, with no
changes to either.
