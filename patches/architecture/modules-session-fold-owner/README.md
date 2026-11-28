# Separate session fold and preview from snapshot mechanics

Place existing Fold and preview implementations in a private internal module
shared by the session-storage writer and projections. Leave persistence,
snapshot pagination and integrity checks unchanged.

Use `source.patch` on pinned Modules upstream and `source-after-stack.patch`
on the cumulative tree in the receipt. Five exact tests per base use local
synthetic journals and in-memory preview; no worker, model or network.
