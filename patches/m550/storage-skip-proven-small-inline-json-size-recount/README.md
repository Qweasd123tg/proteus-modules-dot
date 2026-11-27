# Skip an already bounded inline JSON size recount

For the pinned compact serializer, an inline Value cannot serialize to
more than 32 times the source JSON bytes. A full line of at most 2 MiB
therefore satisfies the existing 64 MiB inline payload limit. Longer
lines use the original exact count. The branch runs only after the
same JSON parse, schema and session checks; no external blob changes.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`: both arms built optimized
libraries and passed 118 tests (one ignored).
The direct witness saw 1→0 count passes on an 86,693-byte inline fixture
and at the 2 MiB cutoff, and 1→1 one byte above it. Typed records and
the tested errors match. These are serializer calls, not measured
latency. The proof and pinned versions are in the receipt.
