# Release replay indexes before finalizing transcript rows

Standalone Core source patch for `024fb944a91382026bb2aa5c7b8da65c284d0305`. Verify the packet with `sha256sum -c SHA256SUMS`; run `git apply --check /path/to/source.patch` in that detached Core checkout before applying. Contextual application to the specific prior Core stack including #926 also passed with exact inverse; no extra patch needed.

Once replay built its rows, keep only those rows and the child-link map. Drop the timestamp, visibility, deduplication and row lookup indexes before enriching row metadata; release the child-link map before normalizing interrupted statuses. This preserves repeated metadata lookups, invocation status/order, and exact row bytes. The compact text and valid warm-cache paths are not the target.

Native release validation: **151 tests per arm**, including full transcript and HTTP unit-test groups. Exact JSON bytes equal on all four inert renderer inputs.

| Bound tool rows | Live bytes before metadata: stock → patched | Live bytes before status pass: stock → patched | Scoped replay high-water: stock → patched |
|---:|---:|---:|---:|
| 0 | 0 → 0 | 0 → 0 | 0 → 0 |
| 1 | 3928 → 3068 | 4807 → 3471 | 4818 → 4315 |
| 256 | 338544 → 236048 | 563568 → 397056 | 564599 → 461072 |
| 4096 | 5415024 → 3776528 | 9015408 → 6352896 | 9031799 → 7376912 |

The synthetic renderer fixture quantifies thread-local requested bytes still live at each boundary, not system PSS, retained allocator pages, production latency, or a full GUI run. Both visibility preparation and earlier decode stages can still dominate a real peak. The receipt contains phase definitions and the exact standalone test overlay.
