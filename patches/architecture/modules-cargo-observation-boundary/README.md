# Separate Cargo output observation from artifact publication

A private helper reads already captured Cargo stdout and reports observations
and diagnostics. Cargo invocation, result and file checks, digests, and
artifact index/report publication still belong to the build function and
run in the same order.

Use source.patch for pinned Modules or source-after-stack.patch for the
cumulative tree in receipt.json. The direct stdout test uses synthetic
records and StringIO. Existing package tests use fake artifacts and mock
builds; no Cargo or module executable ran.
