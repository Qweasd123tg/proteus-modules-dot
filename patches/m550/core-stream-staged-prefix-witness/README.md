# Core: bound the staged display prefix verification buffer

When cold display recovery already has an exact witness for one eligible large staged record, the prefix check now reads and hashes the record in chunks of up to 8 KiB instead of collecting the full line in a second temporary buffer. It still requires the same SHA-256, one final LF, no earlier LF, and physical EOF. A declined probe uses the original scanner, preserving typed fallback and error order for stable input.

This removes one large scratch buffer on the eligible path, not the second file read or hash pass. Canonical storage, formats, record limits, and first rendering are unchanged. A declined probe can add I/O before falling back.

Verified with the pinned Rust 1.95 toolchain on the exact patched Core clone: 3 focused tests and 37 session-store remote tests passed. The 37 include the 3 focused tests. No Desktop launch, latency, application memory, or on-disk codec change was measured.

Apply `source.patch` only to the exact Core preimage in `receipt.json`. No alternate. #577, #633, #660, #665, and #667 are already in this owner.
