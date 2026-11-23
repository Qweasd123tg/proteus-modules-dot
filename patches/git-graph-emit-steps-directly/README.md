# Git Graph: stream finalized drawing steps

Draw each pass once its successor is known, rather than building a
temporary step vector for every graph line. Keep only the latest pass
pending, because a same-row curve can still revise its destination.
Flush it at the end of the line. The patch does not change layout,
colors, clipping, duplicate handling, or stroke order.

The one-file patch targets Extensions
`923077d3967ae7063a6556bc378c09f97abc2854`. Git and GNU patch
forward/reverse checks restored the exact source bytes at zero fuzz.

## Verification

- Rust 1.95.0 compiled both pristine product modules without Cargo.
  Debug and optimized suites each passed 14/14, including 8 embedded
  tests and 6 ordered projection tests: 100 linear and 500 mixed rows,
  pending parents, a wide clipped graph, and 96 deterministic histories.
- Separate tests on copies with byte-identical product prefixes passed
  8/8 in each mode and arm (4 embedded and 4 targeted). They directly
  cover same-row revisions with and without a pending pass, multiple
  revisions, empty and clipped lines, and final flush.
- The unchanged historical #189 suite had the same 7 passes and one
  expected failure in both arms and build modes. The false-parent
  fixture still observes `{4, 6}` rather than `{4}` on row 1. This is
  not a fix for that existing routing defect.

Only the temporary per-line step vector is removed. The final rows and
other graph storage still allocate. No live Git, full Cargo package,
Desktop UI, timing, or process-memory gate was run.
