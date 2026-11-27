# Build OpenAI reasoning summaries without a temporary vector

Keep only the final string rather than collecting a vector of fragments.
No accepted fragments still gives empty text. One is copied directly;
multipart pre-sizes the result from the accepted lengths. Empty entries,
line breaks, Unicode, signatures and the raw provider response stay exact.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. In the optimized offline response
item parser, accepted input removed one 64-byte fresh allocation in these
fixtures. The 64-fragment case also removed four reallocations (1,920
cumulative requested bytes); no qualifying entry was unchanged. Native
39 selected tests per arm, two new parity and allocator fixtures. Both
exact production libraries compiled without overlays.

Use source.patch on the exact base or the verified #895/M650 compatible
source trees. No live provider, elapsed time, or app PSS claim.
