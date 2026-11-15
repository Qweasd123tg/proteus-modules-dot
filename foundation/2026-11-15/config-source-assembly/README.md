# Core config source assembly

Read [REPORT.md](REPORT.md) and [REVIEW.md](REVIEW.md) before using [composed-config.patch](composed-config.patch). The patch is an alternative to #86 Core + #137/#138/#139 on Core `bcbda4435534a296c707a1daa250813d692f68e1`, never an additional layer after those originals.

Publication contains only the reviewed patch, reports and metadata. Baseline/prior source snapshots and all execution/environment logs are deliberately omitted. `SOURCES.json` records upstream identities; its `local` fields name verification-layout locations, not files shipped in this public package.

Observed file checks: 34 input Git blobs and 48 original manifest entries rehashed; two selected application orders produce identical 14 target files with zero fuzz; combined application and reversal restore target/baseline bytes. Independent source review found no blocker in its stated scope. Offsets were accepted; all 24 orders were not tested. Python fixture syntax was parsed, not executed.

Rust tools were unavailable. The 13 retained Rust tests were NOT COMPILED / NOT RUN. No runtime, full integration, CI pass, deployment or benchmark result is claimed. Full-config clone/JSON bootstrap costs, duplicate valid-schema compilation and mixed invalid-schema/collision precedence remain documented. Upstream repositories are unchanged.

The publication manifest covers only the files distributed here, excluding itself. Original evidence is retained unchanged outside this package.
