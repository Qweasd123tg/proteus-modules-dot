# Borrow catalog paths for Desktop tab reconciliation

One standalone Desktop production patch at exact `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and sealed M150 plus #393, #396, #398, #400, #401, #403, and #405. Four exact-source headless lanes passed. No native GPUI, HTTP traffic, or remote work.

## Remove one copy per catalog record

On a successful admitted Core session catalog refresh, Desktop created an owned `chat:<path>` string for every session just to decide which potentially much fewer tabs stay open. The source route issues `GET /sessions`, which contains an ordered stored/live catalog, not just open tabs. Borrow the same lossy path suffix from each received session for the duration of the update; the older spelling is exactly the prefix plus that text. Decoding a tab suffix still uses the existing `tabs::chat_dir`, and lookup uses literal text rather than `Path` equality, which can normalize repeated separators and dot components. Lossy replacement equivalence on invalid native path bytes is unchanged.

The same open-chat/other drivers/documents predicates, activity baselining, async admission gates, generation, stale rerun, pending session-project handling, metadata projection, notify and layout persistence call sites remain. The open-ID set still owns its IDs, the catalog suffix set still hashes and allocates its table, and truly invalid native path bytes still require an owned lossily converted name. No persistent cache, no URI normalization, no serialization format change, and no overall memory or timing claim.

## Exact focused proof

The harness executes complete stock/patched `refresh_sessions`, `set_sessions` and `update_tabs` bodies, real availability logic over modeled providers, exact local `proteus-tabs` and `ChatSpaces`, exact production attention tracker, and complete per-tier metadata projection. Request transport and GPUI live side effects (connection, subscriptions, renderer, actual disk preference writes) are modeled. Normal fixture vectors use round-tripped pinned `AppSessionSummary` wire DTOs. The separate Unix invalid-code-unit fixture is a directly constructed native path witness, not a valid JSON decode.

The checked tab layout includes retained and removed raw IDs, pinned open-only vs pinned missing Core tabs, inactive document and Codex tabs with embedded `chat:`, preview, focus, split ordering, MRU and previously closed tabs. Both `PartialEq` and saved layout JSON were checked against the exact retained oracle; the mocked persistence receiver captured actual serialized `ChatSpaces` content. Core activity/metadata committed in incoming order, while stale/failing replies left both metadata and layout untouched, and accepted coalescing issued only the original single follow-up branch.

| Executed catalog fixture | Explicit prefixed IDs built, stock → patch | Candidate borrowed / owned suffixes |
|---|---:|---:|
| 80 valid UTF-8 session records | 80 → 0 | 80 / 0 |
| 256 records, including one duplicate raw ID | 256 → 0 | 256 / 0 |
| Empty / one valid record | 0 → 0 / 1 → 0 | 0 / 0; 1 / 0 |
| Two exact text aliases including empty Core suffix | 2 → 0 | 2 / 0 |
| Native invalid byte and valid U+FFFD lossy collision | 2 → 0 | 1 / 1 |

These are explicit formation/pointer-shape counts in the temporary harness, not all allocator calls. The complete deterministic 12-line trace across the four arms was identical: SHA `6845072350982a35499365100dc046c29ae8cf99208e93e001b928f6dd869c16`. Cargo JSON selected each exact fresh binary and per-tier local tabs artifact, with executable, library, generated sources and lock bound by SHA before/after invocation. 41 prior Desktop patch hashes were checked, with no conflicting catalog callback coverage. Inherited metadata projection differences between stock/composed remain unmodified and are compiled from their own tiers.

## Reproduce

Use the shared warm offline cache and target, common compiler lock, one job, and both mounts with at least 512 MiB free and at most +200 MiB net growth. Set absolute `CARGO_HOME`, `CARGO_TARGET_DIR`, `R83_BUILD_LOCK` and `R83_RAW_CARGO_DIR` (create raw dir). Final run sampled +4,116 KiB target and +2,408 KiB temporary growth.

    bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS
    bash verify.sh --run WORKSPACE_WITH_PINNED_INPUTS
