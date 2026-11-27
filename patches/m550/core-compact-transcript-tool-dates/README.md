# Store narrower dates for transcript tool calls

Standalone Core source patch for `024fb944a91382026bb2aa5c7b8da65c284d0305`. Verify with `sha256sum -c SHA256SUMS` and `git apply --check /path/to/source.patch` in the stated detached Core checkout. Exact prior source selection through #937 also applies and reverses.

The tool call-date table only reads the timestamp from its first journal occurrence. Keep that timestamp, not the sequence number used by the separate message and part tables. All key lookups/insertion rules, backward-clock behavior, pre-frontier hosted date lookup and strict journal checks are unchanged. This does not optimize repeated key allocations.

Native release validation: **151 tests per arm** including transcript and HTTP groups. Exact returned call dates across eight strictly validated synthetic cases; requested-only or requested/allowed/result (with later clock times rolling back), scoped and full collection agree.

| Distinct call IDs | Lifecycle | Live requested bytes with index held: before → after | Peak while building only that index: before → after |
|---:|---|---:|---:|
| 0 | request only | 0 → 0 | 0 → 0 |
| 0 | request, resolution, result | 0 → 0 | 0 → 0 |
| 1 | request only | 206 → 174 | 206 → 174 |
| 1 | request, resolution, result | 206 → 174 | 232 → 200 |
| 256 | request only | 27664 → 23568 | 37370 → 31226 |
| 256 | request, resolution, result | 27664 → 23568 | 37370 → 31226 |
| 4096 | request only | 442384 → 376848 | 597050 → 498746 |
| 4096 | request, resolution, result | 442384 → 376848 | 597050 → 498746 |

On the native target the value is 8 bytes instead of 16. Retained allocator savings depend on table capacity, not the number of events. Scoped requested allocation sizes are not memory residency, application PSS, or a runtime benchmark. Exact inputs and runner are in the receipt.
