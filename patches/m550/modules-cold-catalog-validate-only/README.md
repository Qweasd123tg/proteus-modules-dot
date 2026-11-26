# Modules: validate a cold catalog without building unused projections

When the session catalog is rebuilt or audited, it still reads and validates the same records in order on JSONL and SQLite. It uses the existing validation-only fold rather than also building usage and model-context projections that this catalog never consumes. Revision, digest, history count, preview, and cache publication use the same inputs. Cache hits, dedicated usage reads and display resume are unchanged.

This removes two unused kinds of derived work from the cold catalog, not a journal read or validation pass. No durable data, storage format, or public wire changes.

Verified in an isolated Rust 1.95 build of the exact Modules checkout and its locked Core dependency: 26 distinct tests passed. The new test covers both backends, comparing normal cold and audit catalog results to a strict display snapshot. The warm control decodes no records. No Desktop timing, application memory or end-to-end speedup was measured.

Use `source.patch` only on the exact Modules owner and path preimages in `receipt.json`. #716 is already present. No alternate.
