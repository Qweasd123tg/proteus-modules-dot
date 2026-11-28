# Share reply format selection between render and update

Both paths derive format from the current transcript row. A retained
view is reused only if its format still matches the row. Existing
renderer selection, layout notifications and fallback stay in place.

Use source.patch for the pinned Desktop tree, or source-after-stack.patch
on the cumulative source. Verification uses local synthetic reply data.
