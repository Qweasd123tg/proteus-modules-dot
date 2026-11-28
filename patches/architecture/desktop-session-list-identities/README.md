# Let the session list own its row and branch identities

Move existing `ItemId`, `OrderGroup` and `branch_key` definitions into
`session_list`. Rendering code depends on those definitions directly.
No composition, layout, selection, navigation or drag/drop policy changes.

Use `source.patch` on pinned Desktop upstream and `source-after-stack.patch`
on the cumulative tree in the receipt. Four exact native tests per base
use in-memory list and drag/drop data; no window is launched.
