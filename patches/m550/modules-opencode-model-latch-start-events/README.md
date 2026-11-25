# OpenCode JS: stop classifying start tags once a stream is started

Reuse the existing ordered list of six start tags. Once the stream-start marker is set, skip future membership checks while still reading the event type at the same point. Preserve the marker set by MessageCompleted, completed-message retention, callback acknowledgment order, terminal count, and before/after-start failure classification. This does not change what counts as visible text.

Four local arms based on exact owner and scoped sources matched across 25 controls. In a fixture of 2,052 native events including 2,048 ordinary text deltas, the six-tag membership lookup ran 2,052 times before and twice after. All 2,051 host acknowledgments and the terminal response matched. Across two runs in the same module, the probe saw 4,104 distinct list identities before and one after.

The actual adapter, local request conversion and collector ran with inert upstream dependencies. These are lookup and receiver counts, not allocations, time, application RAM or a real provider run.
