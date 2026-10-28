# Next increment: opt-in tool/v6 adapter (not implemented)

**Feasible without cross-process redesign:** add `portable_skill_search` to the
existing `portable.skills` tool export. Each call uses fresh `discover`, builds
a request-local **metadata-only** index, and returns a ranked, load-ready
shortlist. This improves discovery output; it does not claim reduced file I/O.
No new cache, provider sharing, watcher or Core contract is needed.

## Exact touchpoints

Base: existing `examples/portable-skill-catalog`, SDK pin `3f36a003` unchanged.

| File | Change |
|---|---|
| `Cargo.toml` | Local path dependency on this library, delivered at a stable sibling path such as `../bounded-skill-index` |
| `src/lib.rs` | `mod search`, `SEARCH_TOOL`, descriptor and invoke arm; keep existing cancellation/error/size envelope |
| `src/search.rs` (new) | Strict args, fresh discovery, digest/fact mapping, ranking and bounded response |
| `host.search.example.toml` (new) | Copy existing offline sample; explicitly add search to `[tools].enabled` |
| `README.md` | Metadata-only coverage, exact load handoff and verification limits |

Leave `Config`, `catalog.rs`, `load_skill`, provider/cache implementation and
original host sample unchanged. Existing sample allowlists exclude the new tool
until the owner enables it. Registration-disabled-by-default for arbitrary hosts
would instead require a default-false config field plus descriptor/invoke guard;
that is broader than the existing sample's host allowlist opt-in.

Contracts: existing `ToolModule::{definitions,invoke}`, `ToolExport`,
`ProcessToolDefinition`, `ProcessToolInvokeInput`, `ToolModuleHost`, `ToolResult`,
and `ToolSafety::ReadOnly`. Preserve untrusted-content/no-execution metadata.
Ship the dependency source; never publish a transient `/workspace/shared` path.

## Arguments and flow

Only `{query: string, limit?: integer}`; required query, default limit 8, allowed
range 1..32, `additionalProperties=false` and `serde(deny_unknown_fields)`.
Schema maxLength 1024 is not enough: enforce **1024 UTF-8 bytes** in Rust too.
Do not accept roots, settings, candidates, source IDs, digests or cache keys.

1. Keep outer 65536-byte invocation bound/cancellation checks. Validate args
   before discovery where possible; ranking revalidates its own bounds.
2. Call `discover(&self.config, &input.skills.disabled, &mut cancelled)` using
   the same current invocation settings as the catalog tool. Existing roots,
   read guards, disabled IDs, model-invocation rules and strict/lenient behavior
   remain authoritative.
3. Decode each existing digest strictly from 64 lowercase hex chars into 32
   bytes. Build source labels `portable:{root_id}` and `SkillFacts` with no body.
   Construct `CurrentSkill` from **that same fresh snapshot**, never model args.
4. Build/search a local index. A local key value is sufficient while nothing is
   retained or shared; do not expose it as catalog revision. Future reuse needs
   a real export epoch/revision/freshness owner, not that ephemeral constant.
5. Resolve hits by exact ID in the same snapshot. Return name/description/source,
   score/coverage and `load_args = {id, sha256, catalog_path: skill.path}`. Copy
   the discovered path; never derive it from a query. Existing load independently
   rechecks current settings, path and full digest.
6. Include `TRUST_WARNING`, `metadata_only=true`, coverage and discovery warnings.
   Warnings mean discovery may be incomplete; even a warning-free no-hit is not
   proof of semantic absence. Do not expose excluded-entry totals unnecessarily.
7. Enforce existing 131072-byte whole output and 262144-byte ToolResult caps.
   Large escaped paths/descriptions can overflow even 32 hits: explicit
   lower-limit error, not malformed/truncated success. Respect smaller host caps.
8. Preserve cancellation as an operation failure, checked again after ranking.
   No hard synchronous interruption or aggregate concurrency quota is added.

This gives a usable tool without touching provider snapshots. Optional body
prefix capture and measured tool-local reuse are separate later increments.
Adapter implementation/build/runtime verification are **not part of this
source-only library delivery**.
