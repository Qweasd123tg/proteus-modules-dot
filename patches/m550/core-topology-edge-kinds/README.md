# Core: borrow edge kinds when rendering the topology map

The edge summary used to clone the kind string for every edge, including repeat occurrences of the same kind. It now counts borrowed string slices from the snapshot. The temporary summary still returns a compact vector in the same string sort order, and the renderer still returns an owned report.

In the six-edge topology produced with no configured modules or tools, full-renderer allocation requests fell from **29 to 23**, and gross requested bytes from 1,850 to 1,712. With 100 fixture tools (172 edges), requests fell from **613 to 441**, and gross bytes from 70,293 to 68,119; peak requested bytes stayed at 25,992. With 2,048 fixture tools (3,419 edges), requests fell from **11,955 to 8,536**, and gross bytes from 1,251,951 to 1,210,490; peak stayed at 449,507. The tool counts are test sizes, not estimates of a typical installation.

A detached Rust test compared the complete rendered bytes, independently checked the sorted counts and measured both the helper and the full renderer across ten fixtures in four paired arms. All outputs matched, including empty, duplicate and Unicode kind names. Returned report bytes retained were unchanged. These measurements do not establish a change in elapsed time, process RAM or GUI behavior.

The single source hunk applies and reverses directly on Core main and the Core revision pinned by Desktop. No prerequisite source patch is needed.
