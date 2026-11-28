# Remove the startup-history dependency on cache publication

The cache layer owns writing each startup representation. Startup history
and the writer both use the same unchanged preview code. Existing cache
layout, checks, write ordering and publication behavior remain unchanged.

The receipt records both exact base trees, five native in-memory tests per
base, and a 4,096-row Full/Plain comparison of serialized objects and read
and write order. No worker, server or external storage was run.
