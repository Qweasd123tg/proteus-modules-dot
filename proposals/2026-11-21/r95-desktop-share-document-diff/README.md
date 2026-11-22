# Desktop: share the complete raw patch for Git documents

One production patch for Proteus Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded`, verified on stock and the sealed M150 Desktop stack through #417.

A Git document's accepted widget already keeps its original whole patch, but the native DiffView stored a second complete copy. The required string now decodes as before and moves into an immutable shared owner. For a newly mounted or changed document, the native view adopts a handle to the same bytes. The update still takes the existing byte-and-metadata equality gate before keeping the new owner. Embedded chat diffs continue to own their String and use the existing borrowed update path.

This is the complete document input, not #413's separately parsed per-file blocks. Existing Copy All callbacks still read the current live document when clicked, including original wrapper bytes, CRLF and the last line without a newline. The per-file Copy callback still owns its historical raw file block. Both clicks still materialize a clipboard-owned String; parser and per-file storage are unchanged. An independently decoded equal declarative root can keep separate equal storage while the older native owner remains, as before. Original String spare capacity can stay with the sharing holder; the document adds a small shared-owner allocation.

## Focused verification

* The original diff unit suites passed **13/13** in each stock arm and **15/15** in each cumulative arm. All four exact protocol and native-seam probes matched. The static gate checked 48 prior patches (disjoint #411/#417 field hunks), 125 locked external package identities and unchanged parser, per-file callback and viewport/reconciliation code.
* At mount and at a changed update, the 165,822-byte synthetic whole Git document lost a separately retained 165,822-byte raw native duplicate. The accepted root and view aliased the same backing. The two boundaries are separate observations; do not sum them into a memory saving. Parsed files/lines, metadata, clipboard and process memory were not counted.
* Equal raw bytes and metadata kept the earlier owner and skipped the existing reparse path. Changed metadata alone kept its original update path, reusing unaffected focus/syntax state. Real parser output, malformed required-field errors, optional metadata and height validation, and metadata-only copy disable were covered. The existing Copy All handler read the new complete source after update; an older per-file handler still copied only its original reconstructed block. Embedded owned-string backing and update/height behavior matched.
* The focused native seam runs exact handoff, parser, reconciliation and clipboard callback code with modeled GPUI entities, focus, viewport and clipboard effects. The real OS clipboard, painted GUI, new engine/dependency builds, latency and overall RSS are not claimed.

`cargo-provenance.json` binds eight fresh Cargo JSON artifacts (four focused probe binaries and four local unit executables) to exact input/lock hashes and before/after executable hashes. `behavior.trace`, `work.log` and `unit-results.log` record the matched behavior, scoped ownership counts and timing-free unit outcomes.

## Reproduce

Run `sha256sum -c SHA256SUMS` here. `bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS` verifies static composition without compiling. Use `--run` with the existing warm locked offline target/cache and shared compiler lock, and set a fresh private output directory (`CARGO_HOME`, `CARGO_TARGET_DIR`, `R95_BUILD_LOCK`, `R95_RAW_CARGO_DIR`). The runner checks disk reserves, caps added disk use, and uses one locked offline Cargo job.
