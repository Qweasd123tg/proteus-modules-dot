# Folded Expand All source proposal

Follow-up to known PR85 files-recovery #1. Apply `folded-expand-all.patch` to Extensions `f82b3ad753cf397f8a931b193aa1943af1ef07a7`, or review/rebase deliberately. No prerequisite patch is required. Text composition with PR145 was checked in both orders.

**NOT COMPILED / NOT RUN.** Ten production lines preserve the recorded folded row's expansion/refresh ancestry without adding immediate listing calls or changing the existing descendant BFS budget. Six added Rust tests are proposals, not passing results. Future refresh reads can increase.

Read `REPORT.md`, `DESIGN-DECISION.md` and `INDEPENDENT-REVIEW.md` for limits, historical dedup and validation requirements. `PUBLIC-FILES.json` lists the intended delivery set. Raw source copies and text-application directories are not intended for publication.
