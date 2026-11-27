# Build storage cache names in one buffer

Append lowercase SHA-256 hex into the pre-sized cache filename. Reuse
the same append encoder for normal owned digests. The exact byte name,
parent, hash input, locator checks, source validation, cache contents,
and atomic replacement/eviction behavior do not change.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. An externally linked optimized
allocator probe observed one fewer fresh Rust allocation and two
fewer reallocations per typed ReadCache, with a hit, missing key and
wrong source fingerprint on both backends (20 fresh and 240 realloc
requested bytes fewer per call in this fixture). Valid round-tripped
cache payload and ETag were compared, with an independently fixed
legacy filename. Native tests additionally compare the exact basename
to an independent lowercase formatter and preserve raw Unix parents.
117 tests passed and one was ignored per arm.

Use source.patch on the exact base. The receipt has a reversible
source-only alternate after #855. Do not stack selectors or extrapolate
these scoped counts to application memory, I/O or latency.
