# Bound Cargo output line splitting in portable packaging

Portable Desktop and Core builds still capture Cargo's complete stdout. Parse
that text in small batches instead of copying every line into one list before
parsing. Normal batches split at an LF within 64 Ki characters; a long record
or unusual separator uses short scanning fragments, keeping CRLF together.
The full captured output on build failure, diagnostics, exit precedence,
exact package binding, and executable checks are unchanged.

Both versions passed 39 existing stdlib tests. Paired synthetic checks also
matched 2,273 splitter cases and 15 exact parser outcomes and diagnostic
traces. In a mocked 720-record case with a 707,912-byte transcript, median
additional parser peak fell from 754,660 to 143,227 traced bytes. A
many-record 11,136,650-byte case fell from 11,213,604 to 168,566. A single
8 MiB diagnostic still takes memory for the current line and decoded JSON;
its measured parser peak changed little.

The capture itself is excluded from these measurements and is not streamed.
The time checks cover only parsing synthetic stdout, not Cargo or native
execution. Ordinary parser time was essentially unchanged in this probe;
the standalone splitter and stress cases cost some extra CPU. This is a
packaging-memory change, not a speed, total RSS, or app startup claim.
