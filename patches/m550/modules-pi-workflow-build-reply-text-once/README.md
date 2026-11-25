# Pi workflow: assemble final reply text in one pass

Collect text fragments directly instead of first filtering the projected answer blocks into an intermediate array. The original newline join, empty text fragments and replacement by the latest answer stay the same. The edit remains before the history checkpoint at the original point in the workflow.

The scope is the installed Pi workflow, not the Core history-opening path. The paired checks exercise the exact workflow with inert SDK/host seams and do not measure end-to-end time or memory.
