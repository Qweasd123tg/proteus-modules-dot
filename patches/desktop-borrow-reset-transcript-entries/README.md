# Borrow previous rows during transcript snapshot reset

The existing row vector already lives through snapshot replacement.
Borrow its rows in the temporary identity lookup instead of cloning
every old text reference up front. Clone a text reference only if its
identified replacement can reuse it. Keep the same duplicate handling,
row keys, timestamps, anonymous fallback, and splice boundaries.

Rust 1.95.0 debug and optimized fixtures each passed 16 tests, including
five unchanged in-tree test bodies per version, 11 labelled comparisons,
and 640 generated old/new snapshots. With 50 old rows, 20 unchanged
matches, 15 changed matches and 15 removals, text reference clones fell
from 50 to 20. An all-unchanged reset still made 50 clones. The temporary
map's value type is 8 bytes instead of 40 on the test target; this is not
a measurement of hash-table allocation.

This affects replacement of an existing Core-backed transcript, not
initial load or the direct Codex live tail. The proof does not measure
text memory retained, elapsed time, or native RSS. No Cargo package,
real session, or app was run.
