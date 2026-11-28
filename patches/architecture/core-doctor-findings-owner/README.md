# Separate doctor findings from CLI orchestration

Keep diagnostic findings, append order and error classification in the shared
CLI findings owner. The storage check uses that owner directly. Doctor still
runs existing checks and formats output and exit status as before.

Use source.patch on pinned Core or source-after-stack.patch on the cumulative
tree. Native fixtures check in-memory findings and disabled/unselected storage;
they do not invoke probing, workers or models.
