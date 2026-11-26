# Keep bounded shell output in a circular suffix buffer

For overflow, keep the same first and last byte ranges in one buffer. A new
chunk writes directly into the retained suffix instead of shifting the whole
suffix at each overflow. Collection makes the suffix contiguous once before
the unchanged byte-drop, UTF-8 and result handling. Raw capture and terminal
consumers still see the original chunks before this preview buffer. The
1 MiB retained-data limit and permission/sandbox paths are unchanged.

Apply `source.patch` to exact Modules commit
`4fa39c3ce94119e36f3ff4a86e28dd2171342aba`. No historical patch selector
touches these files through draft #825.

Pinned native shell-tool libtests: stock 130, candidate 134 passed, zero failed.
Selected output, live pipe over the limit, capture and terminal tests also passed.
Bubblewrap namespace behavior was not qualified on this stand. Three
sandbox-parent tests explicitly report the unavailable namespace in both
arms; conditional sandbox tests do not establish coverage here. Tests include matching the old byte-retention rule,
large-chunk allocation bounds, and split UTF-8 followed by another poll.
This does not claim full application timing or PSS.


An isolated optimized buffer/collect benchmark used synthetic 8 KiB chunks
(no child process, terminal, locks, file I/O, or GUI). Sustained overflow was
4.573 ms → 0.189 ms (nine of nine paired wins). With only one overflow, it
was 28.8 µs → 41.1 µs; the candidate orders the suffix at collection. For
the separate untimed 100 MiB stream, retained/dropped bytes matched exactly,
and the final Vec capacity was 2 MiB → 1 MiB. These are buffer-only results,
not application speed or PSS.
