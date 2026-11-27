# Release workflow-response witnesses before rendering

Standalone Core source patch for `024fb944a91382026bb2aa5c7b8da65c284d0305`. Verify the packet with `sha256sum -c SHA256SUMS`, then `git apply --check /path/to/source.patch` inside that detached Core checkout. Exact prior selection including #926 and #936 also applies and reverses contextually; do not apply twice.

Once response visibility is determined, drop the temporary set of root workflow call IDs before the final scan builds display rows. Keep the global eligibility rules and all separate rendering indexes. A denied request still supplies the same requested-call evidence; nested calls only supply the same per-turn display eligibility. Unlike #936, this drops one prepare-only index **during the transition into rendering**, not after finishing row assembly.

Native release validation: **151 tests per arm** including transcript and HTTP groups. Exact JSON matched across all four strict synthetic interrupted-turn fixtures and both the streamed and materialized implementations. The measured stress fixture has no model responses; existing replay-frontier and nested-scope tests cover response eligibility, dates, and denied and nested cases separately.

| Distinct root workflow calls | Live bytes at entry to scan 4: stock → patched | Scoped replay high-water: stock → patched |
|---:|---:|---:|
| 0 | not reached (2-pass control) | 175 → 175 |
| 1 | 944 → 792 | 3939 → 3787 |
| 256 | 74712 → 52680 | 305587 → 283555 |
| 4096 | 1188312 → 836040 | 4879027 → 4526755 |

These are live bytes requested from the allocator by one synchronous renderer, not RSS, PSS, ordinary runtime latency or a full application result. Work to build the eligibility index is unchanged; the change shortens its lifetime. A valid saved display cache bypasses this cold path. The receipt carries the exact environment-independent test overlay and phase definitions.
