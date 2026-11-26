# Core: coalesce canonical history hash fragments

The fallback canonical message hasher now batches small JSON serializer fragments in a fixed 1 KiB stack buffer. Large fragments still feed SHA-256 directly. The short-message path, canonical JSON bytes, ordered digest per row and digest values are unchanged. This reduces calls into the digest, not the number of bytes hashed, and introduces no whole-message heap buffer.

The exact Semantics crate passed 24 stock and 26 candidate native tests. On 50,000 identical synthetic rows preloaded in memory, the optimized hash helper was faster in all 9 pairs: **18.1% and 11.2 ms faster by paired medians**. The separate stock and candidate arm medians were 63.8 and 50.4 ms. All six fixture classes matched the exact digest oracle on every typed row. No Core application startup, Desktop, storage IPC or process memory was measured. The shipping worker was not rebuilt.

Verify `SHA256SUMS`, then apply `source.patch` only to the exact Core owner/tree and file preimage in `receipt.json`. The older #599 short-message optimization is already present; do not reapply it. No alternate or tested cumulative application.
