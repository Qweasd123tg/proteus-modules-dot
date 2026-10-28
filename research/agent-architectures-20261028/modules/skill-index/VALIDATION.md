# Verification status — source only

Date: 2026-10-28. Build/test/benchmark/CI execution: **not performed**, per user
instruction. No upstream files, running processes or user desktop were modified.
No Cargo lockfile exists: the independent library has no dependencies; a local
Cargo invocation may generate one when the owner chooses to verify it.

## Source review performed (not a substitute for compilation)

- Count and byte caps are checked before tokenization/copying input content.
- Bounded sum additions cannot overflow a 32-bit usize: at most 128 entries,
  each with <=4416 metadata bytes and <=131072 body bytes, and early total cap.
- Body slicing moves down to a valid UTF-8 boundary; an incomplete final word is
  discarded rather than treated as an exact term.
- All metadata passes precede all body passes; order and body selection are
  canonical bytewise ID order.
- The only retained text comprises bounded identity/name fields and term text.
  Long token scratch remains at most 64 bytes, including lowercase expansion.
- Classification occurs after Unicode lowercase expansion; U+0130 and an
  already-lowercase i + U+0307 follow the same combining-mark delimiter rule.
- Metadata term-budget overflow aborts build; body overflow is visible coverage.
- Every current identity is validated before scoring. Disabled/not-supplied IDs
  do not enter either hits or per-search coverage.
- A snapshot/source/digest mismatch returns an error without partial hits.
- Stable score components are integral, and ID breaks ties; no float/HashMap
  randomization, repeated-term amplification, or input-order tie-break occurs.
- No authority cache, filesystem reader, script runner, stale fallback, SDK
  contract claim or performance result is present.

## Local verification matrix for the owner (not executed here)

| Case | Expected outcome |
|---|---|
| Metadata-only `root:git-review`, query `GIT-review` | Exact-name hit; metadata_only count 1 |
| Equal scores from `a:review`, `b:review`, both input permutations | Same `a:review`, `b:review` order |
| Repeat same query term and duplicate text words | No score amplification |
| `проверка` description, query `ПРОВЕРКА` | Lexical match through Unicode lowercase |
| Body `İx`, query `i\u{0307}x` (and reversed) | Same lexical terms `i`, `x`; matching is symmetric |
| Accented composed vs decomposed text | No normalization guarantee; not semantic search |
| Query 1025 bytes / 33 distinct terms / >64-byte term | Explicit query error |
| Empty or punctuation-only query | `EmptyQuery`, not list-all |
| 129 facts/current candidates, giant description/body | Error before content scanning/copying |
| Duplicate build/current ID | Explicit duplicate error, no partial result |
| Metadata terms exceed configured capacity | Entire build errors; no metadata-only truncation |
| Body terms exceed remaining capacity | Metadata retained; body_partial true |
| Body bytes/count cap excludes some documents | metadata_only and body_budget_skipped truthful |
| Tiny prefix ends in a multi-byte character | No invalid slice/panic; body_partial true |
| Prefix `deploy` from actual `deployment` (`complete=false`) | Does not falsely match `deploy` |
| Complete body `deploy` | Final word indexed |
| Disabled ID retained in index but absent from current | No hit and no coverage contribution |
| Newly enabled current ID absent from old index | `CurrentSkillMissing`; refresh/rebuild needed |
| Different epoch/revision or source/digest | Explicit stale/identity error, including unmatched ID |
| Empty current set, valid query | Empty hits and all coverage counts zero |
| result_limit 0 or >32 | `InvalidResultLimit` |
| More than K matching skills | Correct top K; matched_skills > returned_skills |
| Repeated identical build/search | Same order/scores/coverage within same Rust Unicode tables |
| Zero body count/byte limits | Metadata search remains usable; no body instructions returned |

Also verify the future adapter, separately from these pure ranking properties:
current invocation disabled settings; read-policy revocation before/after reading;
root rebinding; expiry/explicit refresh; strict digest decode; body/digest pairing;
atomic snapshot/index publication; cancellation around operations; provider/tool
process separation; structured-output and transport byte caps; fresh load after
search and changed-file recovery. These are **not implemented by this crate**.

Before performance claims, measure cold and repeated builds/searches, retained
and peak memory, read bytes at the importer boundary, rank quality and coverage
on a representative skill corpus. Do not infer filesystem I/O reduction from
token indexing: the importer still needs full bounded SKILL.md bytes for SHA-256.
