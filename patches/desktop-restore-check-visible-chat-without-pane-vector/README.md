# Reuse the pane visibility predicate when restoring chats

Use the existing direct visibility lookup when choosing startup chats.
Both paths check the exact active-tab string in every pane. The direct
lookup skips collecting the panes for each queried chat. Chat order,
remembered command context, detached owners, and which backend the
startup selector requires stay unchanged.

A dependency-free Rust 1.95.0 proof used the exact saved-chat selector,
layout methods and startup routing predicates. Debug and optimized
profiles each passed seven tests covering 12 labelled controls and 640
generated layouts. A validated four-pane fixture with 16 chat tab
occurrences went from 17 to one pane-vector constructions in the
selector. Fresh startup stayed at three in the fixture. Rejected layouts
were used only to check parity outside valid saved state.

The remaining chat enumeration and active-chat fallback work is
unchanged. The counter measures vector constructions, not total
allocations, wall time, or RSS. No Cargo package, backend, GUI, or real
saved profile was run.
