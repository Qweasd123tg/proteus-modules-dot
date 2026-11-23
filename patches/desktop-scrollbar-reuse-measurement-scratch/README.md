# Reuse scrollbar measurement scratch on equal-size ranges

Paging between equal-size resident history windows used to discard and recreate the pending-height and fractional-readiness buffers. Reset both buffers in place only when both lengths match the new range, including its footer slot. Different lengths use the old allocation path.

The full-range no-op, readiness observation cloning and remapping, epoch advance, and dirty reset are unchanged. Returning to the same raw range still rejects callbacks from the old epoch. No history cap, display data, persisted measurement, or thumbnail-cache behavior changes.

Across four synthetic 200-row range moves in the exact lifted code, allocation requests fell from 12 to 4 and requested bytes from 32,964 to 25,728. Both scratch pointers and capacities stayed stable; the remaining allocation per move is the unchanged readiness vector. A total-only growth case with live readiness tokens kept those clones and reduced requests from 5 to 3 (8,257 to 6,448 bytes).

Rust 1.95 debug and optimized each passed 20 tests, including 768 generated comparisons. The harness runs the exact synchronous measurement and readiness code with a scalar Pixels adapter. It does not launch the Desktop app or measure rendering time, RSS, or native startup. The patch applied and reversed with exact bytes and mode.
