# Core: untangle model and behavior selection

A model switch that needs to rebuild the runtime now uses the same pure behavior projection as profile reload and behavior orchestration, without importing the behavior orchestration module. Behavior changes still compose with the selected model. The profile owns mode definitions; the persisted selection, permissions, locking, validation, and external contracts are unchanged.

Use `source.patch` on Proteus-harness/Proteus-core at `024fb944a91382026bb2aa5c7b8da65c284d0305`. Use `source-after-stack.patch` instead on the verified cumulative Core tree through #969; it preserves that stack's existing shared path lock. See `receipt.json` for exact test and application evidence.
