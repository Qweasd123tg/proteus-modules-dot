# Core: borrow initial history for completion review

When completion hooks are active, Core now reconstructs the review history from the original snapshot already owned by the turn recorder or replay fixture. The workflow still receives its own copy at the same point, before the live caller starts its optional timeout. The extra deep clone kept only for active-hook reconstruction is gone. The no-hooks path still makes one owned copy.

The patch does not change the public workflow interface, saved history, hook inputs, checkpoint order, continuation limits, timeout/cancellation handling or privacy rules. Later reconstruction and hook-input copies still exist.

33 focused tests passed on the exact standalone Core patch in an isolated Rust 1.95 build: 1 active review/steering case with persisted and in-memory history and both replacement modes, 30 workflow replay tests, and 2 timeout controls. No application memory, Desktop timing or end-to-end speedup was measured.

Apply `source.patch` to the exact Core revision and four file preimages in `receipt.json`. There is no alternate.
