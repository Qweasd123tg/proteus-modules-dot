# Reuse the packed JSONL digest

Fresh packed writes reuse the SHA-256 already computed for the blob name. A private type binds the digest to the exact borrowed bytes. Chunk hashes, aggregate verification on read, collision checks and publication order are unchanged.

Apply `source.patch` to Modules tree `2e62855233d6ac3465cbf7447b215bda198d366e`. The two JSONL source files are the only changes.

The isolated codec skips one whole-payload SHA pass on a fresh 4 MiB blob. The real worker passed 18 before/after comparisons across both serde_json layouts, including restart and corruption/repair controls. See `receipt.json`. No latency or PSS measurement.
