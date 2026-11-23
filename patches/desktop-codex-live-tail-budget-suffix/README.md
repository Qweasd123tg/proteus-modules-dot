# Count the retained Codex live tail from newest to oldest

When the live tail needs a full recount, add rows from the newest end
until an older row no longer fits. This avoids charging the rows that
are already known to be evicted. Keep the existing row cap, byte cap,
newest-row exception, returned headroom, splice and identity pruning.

A dependency-free Rust 1.95.0 test used exact stock and candidate trim
bodies, transcript methods and charge calculation with inert owned
fixtures. Both build profiles passed 17 tests, including six existing
test bodies for each version, 16 labelled paired cases and 768 generated
windows. In the 50-row nested-tool fixture, 25 rows fit under the 8 MiB
budget. Both versions kept those same 25 rows; charge calls fell from
75 to 26. The 50-row case that already fit still made 50 calls.

This proof covers valid, representable charges. It counts calls to
payload accounting, not retained memory or elapsed time. No Cargo
package, app-server, real session or GUI was run.
