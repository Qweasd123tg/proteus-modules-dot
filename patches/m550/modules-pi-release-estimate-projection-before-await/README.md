# Pi: finish estimating tokens before holding the prepared-context request

Put the existing history projection, first matching usage update and token estimate in one synchronous helper. Only the token count remains in the async function when it starts waiting for context preparation. The logic and order of all operations inside the estimate remain the same. No explicit garbage collection is added to production code.

During an isolated Node reachability probe (forced collection, 8,192 projected rows, inert estimator and held host response), the old function kept the projected array and a distinct projected row reachable. The new function did not. This does not measure memory or latency in Proteus with the pinned Pi SDK.

The patch header identifies the current packaged Modules source. Its exact same hunks apply to the scoped canonical leaf after #742 as well; that leaf's before/after hashes are in the receipt. The witness was run on the scoped composition with #742 and #743, not a full M501 build.
