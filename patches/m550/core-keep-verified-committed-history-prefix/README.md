# Core: retain the verified live prefix when refreshing committed history

Core still reads the committed history and constructs the same typed redacted version of live history. If the live IDs are unique and the durable history exactly matches that redacted prefix without reusing a live ID in the suffix, Core keeps the live values it already owns and moves any new durable suffix into place. An unchanged history keeps the same live buffer. Replacements, truncations, reordering, and ambiguous IDs use the original full merge.

The durable source, privacy rules, and fallback are unchanged. This saves cloning retained rows on the verified path; it does not remove a journal read or the full redaction step. The append may still grow the vector.

In an isolated Rust 1.95 build, 21 focused Core tests passed across history reconciliation, HTTP turns, resume, steering and acknowledged publication. The focused cases exercise retained ownership, exact new values, changed or shortened durable checkpoints, and duplicate IDs. No Desktop timing, application memory, or end-to-end speedup was measured.

Use `source.patch` only on the exact Core owner and `history.rs` preimage listed in `receipt.json`. There is no alternate.
