# Avoid rebuilding an identical packed payload on journal append

When the already verified prefix equals the request, use the request
for repeated-chunk source ranges. Read each new chunk into one 64 KiB
scratch buffer. A mismatch materializes the observed prefix and keeps
checking the original observations, so corruption still precedes a
collision. No on-disk representation, integrity limit or path changed.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. An optimized Linux JSONL fixture
appended distinct Effect and Result records with the same 524,418-byte
synthetic tool-result body. The second append reused the same manifest
and requested 458,882 fewer freshly allocated bytes. Both typed
records round-tripped, and the ordinary unpack control matched bytes
and allocation counts. Both native suites passed 117 tests, one
ignored per arm, including mismatch and late-corruption parity.

Use source.patch on the exact base. Exact source-only alternates
for #894, M650, and M650 with #894 are in the receipt. No PSS,
application latency, live provider or tool execution claim.
