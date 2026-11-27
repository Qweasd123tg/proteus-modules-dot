# Check archive blob references without allocating a comparison path

Compare the exact two native path components and case-sensitive ASCII
digest plus suffix. Preserve the previous Path equality semantics and
the order of digest, path, size and integrity validation. The actual
blob-open path is still built from the checked hash.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. The optimized comparison on a normal
external blob path went from two fresh allocation and three reallocation
requests to zero. The ordinary already-packed archive test also passed
with exact report, manifest and journal parity within each arm. Both
native full suites passed 118 tests, one ignored. The reversible
alternate after #866 passed 116 original tests, one ignored.

No app latency, peak memory or Windows runtime result is implied.
