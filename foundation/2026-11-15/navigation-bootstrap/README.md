# Context navigation bootstrap: reviewed source candidate

Known [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85) files-initialization #1, not a new bug. Read [REPORT.md](REPORT.md) and [INDEPENDENT-REVIEW.md](INDEPENDENT-REVIEW.md).

Desktop-only patch: **+12/-1**, existing NavigationChanged after Context/optional snapshot, before subsequent render. No new protocol. Announced means an attempted send with a process, not a delivery ACK. Extra initial renders remain possible.

**All 10 producer and 3 SDK controls are NOT COMPILED / NOT RUN.** No native UI, real restart, transport, compiler or performance proof. This repository merge publishes documentation and an unapplied candidate; it does not modify upstream or qualify a release.

Split-pane visibility, poll fairness and Copy Path are not fixed here.

## Package and reproduction

- Exact patch, reviewed proposed test sources, final source review and hashes.
- `SOURCE-BLOBS.tsv` maps retained source identities; `REFS.json` pins upstream commits. Raw logs, full source snapshots and temporary working copies are excluded.
- Generated producer fixtures contain only selected methods and stand-ins, not a full source snapshot. SDK controls are proposed additions to the pinned existing host test module.
- To reproduce text generation in an owned workspace, materialize listed Desktop files from `Proteus-harness/Proteus-desktop` at the pinned commit under `sources/desktop/`, verifying Git blob and SHA256 identities. Copy runtime/scopes.rs under `candidate/src/ui/extensions/declarative/runtime/`, apply the patch at that candidate root with zero fuzz, create `regression/generated/`, then use `regression/generate.py`. The script performs text extraction only. Running Rust controls requires a separately available supported toolchain and does not replace native qualification.
- Historical review hashes refer to the original research report/README; this publication adjusts links and excludes source copies. `MANIFEST.sha256` describes the published bytes.

Publication validation independently rechecked all 15 local source Git blobs/SHA256 against retained pinned trees, exact zero-fuzz patch application and candidate byte equality, forward/reverse whitespace checks. No behavioral tests were run.
