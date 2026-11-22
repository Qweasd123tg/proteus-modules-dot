# Focused result

The corrected fixture passed on the pinned stock source and cumulative Desktop
through #449, with and without the same exact source patch. Each of the four
arms passed 72 real tabs tests and four focused headless tests. All ten
scripted schedule/result records were byte-identical across the four arms.

| Isolated copy case | Allocation requests | Requested bytes |
|---|---:|---:|
| Matched, deserialized 72 tabs and four roots | 108 → 0 | 8,504 → 0 |
| Matched, additional in-memory MRU/closed history stress | 200 → 0 | 13,569 → 0 |
| Fallback, deserialized | 108 → 108 | 8,504 → 8,504 |
| Fallback, in-memory stress | 200 → 200 | 13,569 → 13,569 |
| Empty, matched or fallback | 0 → 0 | 0 → 0 |

The meter covers only the existing redundant clone or its replacement,
with prebuilt state. Both stock and cumulative measurements agree. The
required copy for fallback, the active-layout copy and window registration
copy are unchanged. These are allocator requests, not memory footprint,
startup seconds, or a 50k history result. No Core, actual preboot, native UI,
network, terminal or PTY ran. Initial source staging was 576 KiB. Sampled
maximum stand drawdown was 12,836 KiB, not a general capacity guarantee.

The first admitted compile stopped in the headless fixture: its lifted method
was included one module too high to resolve the sibling preferences module.
The separately admitted correction only nests that include to mirror the real
source module. The product patch, lifted method bytes and runner did not change.
The recovered fixture and provenance are included; original raw failure
material remains private.
