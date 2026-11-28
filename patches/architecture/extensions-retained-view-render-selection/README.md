# Share retained-surface traversal without sharing scope policy

Session refresh, window appearance refresh, and poll each keep their existing
eligibility rules. The shared traversal snapshots eligible view IDs before
callbacks, gives the requested eligible view priority, and looks up each view
live when rendering it. No new public API or permission behavior.

Use source.patch on the pinned Extensions revision, or source-after-stack.patch
on the cumulative tree. Use the receipt to match bases and synthetic checks.
