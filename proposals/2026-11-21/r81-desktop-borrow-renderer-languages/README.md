# Borrow registered renderer names across Desktop reply renders

One standalone Desktop production patch, identical on exact Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and sealed M150 plus #393, #396, #398, #400, #401 and #403. Four exact-source headless arms passed. No native GPUI, extension process, timing, RSS, or remote work.

## What changes

Visible user/assistant reply rendering calls `Replies::part`. Even when the existing view and source are unchanged, stock clones each installed language name before the retained-view check, and retains owned names per row when a snapshot is stored. The map of language providers still needs the same names in the same order. The installed manifest already lives in an immutable, process-lived `Box::leak`, and `installed(id)` already returns its `&'static Installed`. Borrow its names without a new cache, leak, lifetime extension or mutable shared storage. Comparison remains value-and-order equality, not address equality. A direct nested lookup can stop at the first enabled claimant without collecting the language vector.

The same preference ordering and enabled/current-installed checks remain. An asynchronously changing catalog is not made atomic by this change. Multiple packages may claim the same valid name, with the first winning; repeated saved-order IDs, contributor-map entries and list duplicates retain their earlier semantics. The same JSON context owns its key and list strings once serialized. Full body media-format selection, native callbacks, renderer generation, source admission/ACK, queue, and application parsing are unchanged. Existing tuple vectors and catalog/prefs traversal still do work; this is not an all-allocations or overall-memory claim.

## Exact focused proof

The harness reads actual sealed bundled package manifests and the referenced skill file from fixture paths, using the actual Desktop manifest schema and filesystem discovery. It executes the production catalog `rescan`/`entry`/`installed` including the existing lifetime assignment, preference ordering/enabling, full `Replies::part`/retain paths, exact context and source-revision logic, inline selector, and the actual serialized `Outgoing::Render` variant. Only the GPUI entities, icon enum subset, process sender, viewport, and callback effects are modeled; app focus, real refresh callbacks, lifetimes of native mounted views, and actual extension dispatch are not exercised.

Five real bundled registrations are included: JSON's `json-render/svg`, Markdown's `md/markdown`, and Mermaid's `mermaid`. The warm runs first seeded eight existing rows, half Markdown and half plain, then used the exact retained code:

| Executed fixture | Explicit name clones, stock → patch | Language entries yielded, stock → patch |
|---|---:|---:|
| Eight warm retained renders | 40 → 0 | 40 → 40 |
| Forty warm retained renders | 200 → 0 | 200 → 200 |
| Direct `md` after JSON registrations | 5 → 0 | 5 → 3 |
| Last registration or missing (each) | 5 → 0 | 5 → 5 |

The counts exclude cold setup, other renderer work, serialization and catalog/tuple allocations. The retained names alias the existing catalog buffers in the candidate. Same-value user override with different addresses still skips revision/update; a changed manifest refreshes the same retained view and increments source revision once. A distinct shadowed duplicate updates the retained registration tuple but sends no new wire/revision. Disable/reorder, repeated saved IDs, malformed or same-package duplicate manifests, exact case/Unicode query misses, plain fallback, non-object contexts and opaque ordered JSON all passed.

Each arm produced the same 36-line trace, including 19 case receipts and 17 exact JSON lines: SHA `1a0c2eed755047c0b15886512bd081a48c773fe51f8fd335a29cb8e13b418e7a`. Four fresh non-test Cargo JSON artifacts with the embedded source-tier stamp are bound by exact executable SHA before/after invocation, generated source/build lock and manifest/fixture inputs. No repeated parse/startup, general allocation, process count, or latency claim.

## Reproduce

The verifier checks the source seals, 40 earlier Desktop proposal hashes, 125 exact Cargo dependency identities, patch forward/reverse/whitespace, and unchanged catalog/retained-policy/wire contexts. Use the existing warm offline cache, a common compiler lock, one job, two mounts with at least 512 MiB free and maximum +200 MiB net growth. The admitted final gate's sampled growth was +4,400 KiB on the target mount and +1,952 KiB on the temporary mount. Set absolute `CARGO_HOME`, `CARGO_TARGET_DIR`, `R81_BUILD_LOCK`, and `R81_RAW_CARGO_DIR`; create the raw directory first. The fixture sets package directory and isolated XDG paths only on the launched probe, never user config.

    bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS
    bash verify.sh --run WORKSPACE_WITH_PINNED_INPUTS
