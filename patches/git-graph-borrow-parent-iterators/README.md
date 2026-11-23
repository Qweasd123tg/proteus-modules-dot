# Git Graph: stream borrowed parent hashes into layout

Send each commit and its ordered iterator of borrowed parent hashes directly into the layout engine. This removes the temporary outer projection and the per-commit vectors of parent references. It keeps the same filter, first valid parent, duplicate order, lane layout, and pagination. The raw parent records used by the HEAD affordance are unchanged.

The exact old projection had 101 nonempty backing vectors for a 100-row linear page and 501 for a 500-row accumulated fixture, including the outer vector. The new projection constructs none of those vectors. The existing graph structures still allocate. This is a source-scoped witness, not a process memory or performance benchmark.

Verified on Extensions **923077d3** and with #523 in both patch orders. Fifteen paired Rust 1.95 tests passed in debug and optimized mode in both source tiers. They run the exact graph modules and the lifted feed with inert values. No live Git, Serde, extension package, or Desktop was run.
