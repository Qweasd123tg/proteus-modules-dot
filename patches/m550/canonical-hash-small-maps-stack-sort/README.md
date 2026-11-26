# Sort small canonical hash objects without a heap vector

For objects of at most 12 entries that still require sorting, sort borrowed
pairs in a fixed stack array. Keep the direct ordered path, the larger-object
fallback and the exact recursive ordering, bytes, SHA-256 and limits.

Apply on exact Core `fc0297620c2b6d6d8ade8f524df6a4b99d6fae8b`; #799 is already integrated.
Both optimized native hash modules built and four tests passed in each arm.
The preserved 50-row owned historical leaf dropped from 51 to 1 Rust
allocator requests (7,264 to 64 bytes requested) for the hash. Ordered,
larger-object fallback, current latest-page and pack-envelope controls did
not change. Canonical serialized bytes, digests and inclusive limits match.
This is not a full history opening or a process-memory measurement.
