# Focused result

All four arms passed 36 tests each, including four focused cases, the
production SVG validator, and seven production cache and dimension tests.
The four full behavior records matched byte-for-byte on exact stock and
cumulative Desktop through #451, with and without the same source patch.

For the 43,914-byte synthetic UTF-8 SVG, the focused probe found two
source backing allocations before, one after. The original payload
buffer was moved, not copied. Allocation requests and net requested live
bytes from the local test-only Rust allocator:

| Case | Requests | Aggregate requested bytes | Requested live bytes |
|---|---:|---:|---:|
| Decode + first prepare | 52 → 51 | 1,556,882 → 1,468,976 | 88,054 → 44,126 |
| Decode only | 32 → 33 | 801,740 → 801,780 | 43,914 → 43,954 |
| Independently re-decode the same SVG and retain the reused equal key | 87 → 86 | 2,402,724 → 2,270,880 | 88,126 → 88,152 |
| Tiny 6-byte SVG, decode + first prepare | 34 → 33 | 5,257 → 5,171 | 234 → 218 |
| Inert renderer refusal, preparation only | 4 → 3 | 563 → 86 | 24 → 24 |

The first prepared case saves 43,928 requested live bytes; the equal
re-decode control keeps two distinct buffers and adds 26 live bytes.
The extra Arc allocation costs 40 bytes independently of SVG length in
this x86_64 fixture. No global dedup, native RSS or cold-start result is
claimed. Only synthetic controlled data and inert renderer/bitmap effects
were used. Peak sampled stand drawdown was 16,248 KiB; it is a run-specific
capacity receipt, not a general requirement.

The first gate stopped before tests at a fixture module-doc placement
error. The second gate stopped on an incomplete inert icon inventory
and a mismatched case-normalized error hint in the fixture. Separately
reviewed fixture-only diffs are included. Neither changed product source,
validation, lock, or the execution runner. Both raw failed attempts were
preserved privately.
