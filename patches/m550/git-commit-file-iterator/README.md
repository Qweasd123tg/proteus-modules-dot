# Git commit inspector: stream changed-file references into the tree builder

The inspector already has a slice of changed files. The root projection now passes that slice directly to the private tree builder instead of collecting a second temporary vector of file references. Recursion reads the existing folder groups in the same order. The files, grouping, status, selection, and serialized widgets are unchanged.

One detached Rust proof compared 11 fixtures, 44 allocation-bracketed ABBA operations and 66 ordered serializations. Each nonempty projection lost one allocation. For 128 changed files, total and peak requested bytes fell by 1,024 each. At the Core route cap of 1,000 files, they fell by 8,000 each: gross 3,427,874 → 3,419,874 and peak 2,085,103 → 2,077,103. Empty input and the bytes retained in the output were unchanged. This does not measure a real git command, UI latency or whole-process memory.

**Apply after [#691](https://github.com/Qweasd123tg/proteus-modules-dot/pull/691).** Both measured arms include #691's separate singleton-group optimization. The changes round-trip after that prerequisite on both the pinned Extensions owner revision and the Desktop package pin; this patch alone does not apply to their untouched files.
