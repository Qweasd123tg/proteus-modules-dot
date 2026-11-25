# Core: use the existing render scan to index a committed display append

The accepted committed-append path used a separate scan of the private staged records only to collect identities for the next display prefix. Reuse the renderer's existing first scan instead. Independence is still checked against the old prefix before rendering. Index the original records before stripping retained checkpoint rows for display. The current publisher keeps the updated index private and drops it on failure.

This removes one scan and typed decode of the staged display records, not a read of the durable journal. The remaining validation and fallback paths are unchanged. This patch does not change session format, public wire, startup, or storage writer acknowledgments.

On pinned Rust 1.95, 17 append tests and one acknowledged publication test passed. One test asserted three scans and 15 decodes for a five-record committed stage; the former source had four scans and 20 decodes for that fixture. This is a test of the work performed in that path, not a measurement of wall time, memory, or Desktop.

Apply `source.patch` only to the exact Core owner and two path preimages in `receipt.json`. No alternate.
