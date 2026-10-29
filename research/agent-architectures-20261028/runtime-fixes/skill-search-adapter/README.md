# Portable skill search adapter

`portable-skill-search.patch` adds `portable_skill_search` to the existing
`portable.skills` tool/v6 export. Base: PR #57 commit
`a64384d6ae8a3810d87ece435f8554d75e7eedf8` in
`Qweasd123tg/proteus-modules-dot`. Apply from repository root; the required [library](../../modules/skill-index/README.md) is included at
`research/agent-architectures-20261028/modules/skill-index`. The path
dependency and its dependency-free Cargo.lock entry are included; SDK pin unchanged.

- Strict `{query, limit?}`; fresh existing discovery with invocation disabled IDs.
- Request-local metadata-only index; ranked labels/coverage and exact
  `{id, sha256, catalog_path}` load arguments. No body search/cache/process sharing.
- Existing cancellation, output envelopes and independent load validation remain.
- Original host sample unchanged; `host.search.example.toml` explicitly enables
  search. This is host-allowlist opt-in, not a default-false module config gate.
  The template is a **legacy SDK/Core `3f36a003` integration fixture**, retaining
  the historical aggregate `proteus-reference-module` from the original sample;
  it is not a current standalone shipping profile or a compatibility claim.
- Only the existing wire fixture is extended: three descriptors and exact
  search/catalog load-argument parity. No new harness.

Checked: exact baseline Git blob hashes, TOML parsing, lock entry consistency,
unchanged discovery/config/default sample, manual source review and
`git apply --check --whitespace=error`. **No Rust, product, tests, benchmarks or CI
ran.** Lock compatibility and runtime behavior remain for local validation.
Tool/v6 does not expose the host output cap; consumers must still reject
`output_truncated` before parsing JSON. No I/O or speed improvement is claimed.

This adapter does not require or apply the separate provider snapshot patch.
