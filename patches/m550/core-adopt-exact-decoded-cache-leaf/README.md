# Reuse an exact decoded Core cache leaf as the result

When the requested range is exactly a whole logical leaf, return the
already-decoded row vector if its capacity matches its length. Partial
and spanning requests still assemble their original bounded result.
Header, hash, decode, count and source checks are unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. In checked release warm latest and pinned reads,
an aligned 50-row transcript page avoided one allocation of 32,000
bytes. The unaligned two-leaf control retained all previous allocations
and returned the same rows. Packed and ordinary complete logical leaves
can reuse their exact vector; partial and mixed controls still follow
the old row-by-row collection path. Ordered cache reads did not change.

Each release arm passed 25 targeted view tests. No app latency or
resident memory measurements were taken. For strict full-index tooling
after #909, use the index and final hunk offsets in the receipt; code
hunks are unchanged.
