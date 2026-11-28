# Let the transcript module own completed history

Move the existing completed-history data type and its vector conversion from
event publication to the existing transcript module. No runtime behavior,
protocol or history format changes. The reconnect fixture now verifies the
older-history cursor survives rejection of a stale refresh.

Use `source.patch` on pinned Core upstream or `source-after-stack.patch` on
the exact cumulative tree in the receipt. Four in-process event fixtures
were compiled and run on each base, without real models or storage workers.
