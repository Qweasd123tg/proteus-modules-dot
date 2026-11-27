# Share the immutable export list across schema discovery
Core base: `024fb944a91382026bb2aa5c7b8da65c284d0305`. This is a standalone Core source patch, not a Dot runtime release or a package directory to copy into Core.

Run `sha256sum -c SHA256SUMS` here. In an isolated checkout at the stated Core base, check `git apply --check /path/to/source.patch` and then apply the same file. It also applies directly to the exact tested previous Core selection (see receipt); there is no alternative patch to apply after it.

`ModuleCatalog` still accumulates descriptors in a mutable Vec. Once assembly transfers ownership, the private `RuntimeRegistry` field holds that existing buffer behind one Arc. Settings discovery captures the Arc instead of cloning every descriptor and nested binding config before the existing blocking scan. Component ordering, first representative per component, broker and manifest access, and returned schemas and errors are unchanged. Runtime registry snapshots share this same immutable field; the isolated metric below is for the Settings capture only.

This costs one Arc allocation per registry generation, even with no exports. If discovery outlives both the cancelled waiter and the old registry, already-visited export descriptors can stay owned until the blocking scan ends. The previous code also continued the scan; this change does not cancel or spawn additional requests.

No real model provider or remote service was used. Allocation requests and requested bytes are not process PSS, live memory, startup/GUI time, or the cost of schema IPC.

Native release validation: 151 tests passed on each arm (registry including the isolated probe, Settings builder, HTTP). Existing fixture-based tests exercised reconnect and opted-in idle release; no complete Desktop run.

| Synthetic exports | Capture allocation calls before → after | Capture requested bytes before → after |
|---:|---:|---:|
| 0 | 0 → 0 | 0 → 0 |
| 1 | 13 → 0 | 1036 → 0 |
| 20 | 241 → 0 | 20730 → 0 |
| 64 | 769 → 0 | 66358 → 0 |

One-time setup requested 40 bytes for the shared wrapper. The 20-export synthetic case is deliberately richer than a normal checked-in profile; do not generalize its bytes to user profiles.
