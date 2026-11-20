# Core: reserve the already-counted history-page buffer

Base: Proteus-harness/Proteus-core `048378da7cbe890d8bf8a0152e55eb28ecb5013d`. Use `git apply --check` before applying the included source diff. This proposal does not change Core upstream.

Start the historical leaf's compact JSON buffer at the already counted size. That count is local and already passed the page-size cap. Retain the length check and the original singleton fallback. No change to JSON, hashing, page limits, cache verification or pack format.

In a release Rust harness using the actual page/pack source and typed rows, 450-row text and mixed fixtures each cut reallocations from 97 to 35. Total requested allocation bytes fell by 320,996 and 266,668. The harness verifies identical manifests, payloads, hashes and readback, plus cap and mismatch controls. No-archive and latest-only arms had identical allocation counts. A deliberately overestimated custom raw serialization increased requested allocations by 245,735 bytes and still used the correct standalone storage path; that synthetic DTO is not the current typed transcript caller. These are allocation requests, not end-to-end latency, RSS or on-disk changes.

The two independent allocation changes were also applied together for Core remote-view regression tests: 16 passed (including missing and stale cache, append, packed and over-budget pages). The isolated A/B attributes only the named change.
