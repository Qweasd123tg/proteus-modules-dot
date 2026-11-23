# Parse each manifest once during the license scan

Keep the initial workspace read and the sorted manifest scan. Reuse
the parsed `package` for license resolution and the literal vendored
MIT check. No change to accepted licenses, notice or symlink checks,
Apache source annotations, or diagnostic order. Inherited workspace
MIT still does not qualify for the vendored MIT exception.

Exact Desktop `f8cc40177ad3ab3d8ec36447a899332778f03268`: the existing
license suite passed 7/7 before and after. Eleven paired synthetic
trees matched all ordered diagnostics or the exception type and
message. The passing mixed fixture used 11 → 6 manifest reads and
parses; the ordered negative fixture used 16 → 8 with the same nine
diagnostics. Notice and Rust source reads were unchanged.

Counting the actual tracked manifests (not an elapsed-time or native
measurement), a full stable-tree scan goes from 25 → 13 manifest reads
and parses for Desktop and 40 → 21 for its pinned Extensions. Both base
and candidate counts include the separate root workspace read. For a
manifest edited concurrently, package checks now use one snapshot rather
than comparing reads at different times; this does not make the entire
workspace validation atomic. No Cargo, native client, package install,
or publication was run.
