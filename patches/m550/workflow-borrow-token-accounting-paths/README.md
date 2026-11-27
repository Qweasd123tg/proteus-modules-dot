# Count UTF-8 request paths without formatting a String

Context and FileRef estimates only use the displayed length. For UTF-8
borrow the path and read its byte length. For non-UTF-8 keep the exact
old display formatting. This changes no path passed to an adapter or
the compaction estimate.

Base: Modules f4bd470def2255f3459b7a42b50e96d0faa0bbf1.
Both arms passed five focused tests and built as optimized libraries.
In a prebuilt request with 512 context/file pairs, the estimator's
allocation requests went 1542→518 and requested bytes
42148→4260. Category results match for missing, empty,
Unicode and Unix non-UTF-8 paths. No whole-app measurement.
