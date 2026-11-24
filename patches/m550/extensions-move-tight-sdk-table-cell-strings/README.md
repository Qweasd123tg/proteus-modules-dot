# SDK tables: transfer tightly owned cell strings

The SDK table builder now moves already-tight cell strings into the widget instead of making a second copy. Strings with spare capacity still use the same tight-copy behavior. Table keys, column and cell order, ragged rows, and retained storage stay the same. The SDK serves Usage per-model and per-request tables and Context cards; their callers are unchanged.

A scoped Rust witness checked the real builder with the pinned preserve-order serde_json dependency. One test passed across 11 fixtures and 44 allocator ledgers. It required exact ordered JSON bytes, identical string and array capacities, identical retained requested bytes, and verified pointer reuse for tight cells. In a 100-row Usage-shaped fixture with 400 tight cells, peak requested bytes fell from 74,077 to 43,328, gross from 74,077 to 70,181, and allocation requests from 1,013 to 613. In the long-payload control with two tight cells totaling 192 KiB, peak fell from 395,157 to 197,832. An all-slack control requested the same gross bytes and allocation count, and released input storage earlier.

The witness includes input allocations to account for transfers. It does not measure the complete panel, GUI, wall time or process memory. The single SDK hunk applies and reverses on M462, the Extensions owner revision and the Desktop package pin without prerequisites.
