# Preserve the logical folded-row expansion invariant

Known PR85 files-recovery #1, not a new finding. This is an isolated source-only design; no Rust tests or runtime have run.

The selected row's public path is the deepest folder in a folded chain. `heads` already records the first folder represented by that row. Ordinary `expand` starts at the head within its existing CHAIN loop, but `expand_all` starts only at the deepest path. Partial invalidation then misses the ancestors even though the user expanded that logical row. The separate maximal-fold boundary is not generalized: fold can follow CHAIN edges while ordinary expand marks at most CHAIN folders.

Proposed narrow change: before the existing Expand All BFS, when `heads` contains that exact row path, add its recorded folded ancestors to `expanded`, using existing `paths::parents` and `paths::within`. Stop at the known head. This step performs no listing. Keep the BFS start at the supplied deepest path and retain its existing depth/count limits and error handling.

Do not call `expand` first: it can issue extra reads outside the Expand All listing counter. Do not start BFS at the head: that would spend the existing descendant depth/count budget on the folded prefix. Do not call unrestricted `reveal`: it would open every parent even for a plain hidden path with no known folded-row mapping. Do not reload all collapsed folders on every poll.

The narrow guarantee is membership of the already-recorded folded row's ancestors in expansion/refresh intent. A plain/root path without a recorded head is unchanged. The recorded mapping may have aged since the last render; this does not add a second scan or guess a new fold from current filesystem state. Subsequent ordinary listing/pruning remains authoritative. This proposal does not repair root-error caching, error-to-absence interpretation, unknown malformed paths, or all descendant-pruning cases.

Cost: `paths::parents` first allocates the whole ancestor vector, even though only the recorded folded prefix is selected; its cost depends on overall path depth. The change adds expansion-set entries for the recorded chain and intended future refresh work for those ancestors. They can then bypass LOOKAHEAD as expanded folders. The existing Expand All BFS admits at most EXPAND_ALL folders and reaches at most CHAIN descendant depth; the new ancestor-membership step does not consume that descendant budget or call the loader. There is no new total bound on all later rendering/polling work and no latency/RSS claim.

Ordinary `collapse` already removes the folded chain. `collapse_all(deepest)` retains its current deepest-subtree scope and can leave the folded ancestors expanded, as it already does after ordinary `expand`. Do not claim symmetry of every collapse operation.

PR145 changes failed-listing knowledge separately. The patches must be composition-checked because they touch the same tree and test files; this is not an assertion of runtime compatibility. No prerequisite is assumed until those text checks complete.
