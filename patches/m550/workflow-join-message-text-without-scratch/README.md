# Join response text without a temporary list

For multiple text parts, count the UTF-8 lengths and line separators,
then write directly to one sized String. Empty text segments still
contribute separators, non-text parts are skipped, and empty-response
and tool-result fallback rules are unchanged.

Applies to Modules f4bd470def2255f3459b7a42b50e96d0faa0bbf1.
Both exact trees built as optimized libraries and passed seven focused
offline tests each. At two prebuilt parts the isolated join requested
2→1 allocations/reallocations; at 64 it requested 6→1.
Both produced identical bytes. The first pass visits remaining
part descriptors again, not their text bytes. No timing or PSS estimate.
