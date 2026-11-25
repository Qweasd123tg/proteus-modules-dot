# OpenCode workflow: reuse the filtered history when no instructions are inserted

The BeforeModel hook already builds a fresh array after dropping stale derived instruction messages. Reuse it when no synthetic message is inserted, instead of pushing every canonical message into a second history-sized array. On the first insertion, copy the prefix and resume building a separate output. Both paths preserve the number of semantic history passes and never mutate the caller's array.

Existing path deduplication, synthetic content construction, stable IDs, source-event order, and treatment of stale projections stay the same. This applies to profiles using the OpenCode prompt hook, not to every worker or Desktop startup.

For a history of N canonical messages with no insertion, the old path produces two N-entry arrays while the patch uses one, excluding the caller's input. This count is not a JavaScript heap, latency, or whole-application PSS measurement. See the receipt for verification and scope.
