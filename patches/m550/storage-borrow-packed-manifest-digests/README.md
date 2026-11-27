# Borrow plain hashes while reading packed storage manifests

Parse plain digest strings as slices of the already loaded JSON.
Escaped strings remain supported with the same owned decoding path.
The writer continues to emit exactly the old compact format. Paths,
limits, chunk order and verification are unchanged.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. For legacy packed 50,000-message
history the optimized JSONL ReadRecords probe made 529 fewer fresh
Rust allocation requests (33,856 requested bytes); at 5,000 messages,
53 fewer (3,392 bytes). Reallocation counts and typed history tails
matched on both arms. The exact plain large manifest parser witnessed
530 to one fresh requests; escaping and parser error parity tested
separately. The full native suite with the additional manifest case
passed 117 tests, one ignored per arm.

Use source.patch for the exact base. The receipt includes exact-tree
alternates for #854/#855/#875/#876/#884 and for the M650 selection.
The first alternate also passed the unmodified storage suite (116
tests, one ignored). No measured app latency, PSS or I/O claim.
