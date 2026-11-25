# Core: remove an extra path copy when listing sessions

While attaching activity to stored sessions, Core now passes the copied locator directly to the same canonical key helper. It drops a redundant intermediate copy and keeps the existing canonical key, output buffer, stable order and live-session handling. Both `/sessions` and `/sessions/current` use this assembler.

A detached Rust comparison used the complete stock and candidate functions, real DTOs and path resolution, and deterministic storage/runtime fixtures. All ten fixtures returned identical serialized results or matching errors. These included stable sort ties, symlink aliases, live and pending sessions, and failures from storage and transcript reads.

With 100 stored sessions in the fixture, allocation requests fell from 1,215 to 1,115 and gross requested bytes from 233,993 to 229,393. With 2,048 stored sessions, requests fell from 24,600 to 22,552 and gross requested bytes from 4,663,565 to 4,569,357. In the 2,048-session fixture that saved 94,208 gross requested bytes; the peak fell by only 46 bytes. Retained requested bytes were unchanged in all fixtures. These are allocations during the measured assembler call, not whole-process RAM, end-to-end performance or normal catalog sizes.

The one-hunk patch applies and reverses directly on Core main and Desktop's packaged Core revision. It has no prerequisite patch.
