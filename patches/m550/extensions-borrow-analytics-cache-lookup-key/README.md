# SDK: borrow keys when looking up cached analytics

On a cache hit the SDK no longer copies the request path or the selected session. For an empty query, as used by the Usage panel, the lookup also borrows the existing "[]" key. Nonempty queries keep their original debug-string format, including parameter order and duplicates. On a miss, the SDK owns the key only after a successful load. Session selection, entry expiry, LRU order, cache budgets and the returned shared value are unchanged.

A scoped Rust witness ran the five existing analytics tests on each implementation and one comparison test using a deterministic Host. Across eight empty-query hit fixtures, scratch allocations fell from 1–4 requests (8–36 bytes) to zero. With a selected session and two ordered query pairs, requests fell from 6 to 3, total requested bytes from 75 to 56, and peak requested bytes from 51 to 32. The remaining allocations matched query formatting alone. The comparison checked exact serialized replies, shared-value identity, cached key order and byte accounting.

These are allocations during a cache hit, not the memory retained by the cache, whole-process RAM, network traffic or elapsed time. The patch applies and reverses directly on Extensions main and the Desktop-packaged Extensions revision, with no prerequisite patch.
