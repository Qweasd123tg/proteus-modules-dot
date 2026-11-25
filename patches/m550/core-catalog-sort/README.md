# Core: release session deduplication scratch before sorting

The session catalog no longer retains the set of owned canonical keys while stable-sorting the final rows. The set is still used for every existing stored and live-session check and is dropped only after its last use. Session admission, ordering, route selection and output are unchanged.

A detached Rust test used the original catalog assembler and selected GET routing code, with real contracts and deterministic service fixtures. All 12 paired cases and 15 route projections matched. With 2,048 shuffled stored sessions, live requested bytes at the stable sort allocation fell from 1,295,290 to 940,970 (354,320 bytes, 27.4%). The earlier whole-call peak stayed at 1,315,381 bytes. Allocation count, gross requested bytes and retained bytes stayed the same. This was not a full HTTP, application RAM or latency measurement.

The patch applies and reverses on both owner revisions and composes with #715 in either order.
