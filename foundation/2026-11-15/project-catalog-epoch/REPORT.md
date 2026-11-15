# Project catalog admission: bounded PN-1 source proposal

2026-11-15. **Uncompiled proposal, not a verified UI fix.** No Rust test,
native window, live driver, HTTP request, session creation/deletion, or project
code execution was performed. No upstream or live user repository was changed.

## Identity and deduplication

- Desktop main: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
- Delivery main: `b14f874a165fd0ef83d8387db3af26626a194212` (through PR143).
- This addresses the already reported **PN-1** family in PR85
  `research/proteus-continuous-audit-2026-11-13/evidence/project-navigation/REPORT.md`.
  It is not a new independent finding or a fresh reproduction of that report.
- The prior `candidate-focus.patch` concerns PN-2 focus, not catalog admission.
  This proposal does not change focus, chat insertion, or deletion code.
- Sixteen source/doc files match the pinned Desktop Git blob hashes exactly.
  `SOURCE-HASHES.json` and `EXPECTED-BLOBS.json` record the comparison.

## Existing contract and missing boundary

`DESIGN.md` explicitly says stale catalogs must not return a deleted sidebar
row, while a later user destination prevents an old project response from
navigating. These are two independent conditions, not one generic freshness bit.

`Workspace::session_catalog_epoch` documents the former condition. It advances
when deletion starts, finishes, or `forget_chats` receives deletion cleanup.
Normal `refresh_sessions` and Codex catalog paging reject responses with a
different epoch. Current `open_project` does not capture that epoch: the Core
callback calls `set_sessions`, and the Codex callback mutates summary rows,
before `finish_project_navigation` checks navigation generation. Thus a later
navigation can correctly prevent selection while the same callback still
admits pre-invalidation metadata. This source chain is unchanged from PN-1.

This concerns **sidebar metadata**, not recreation of deleted backend history.
The earlier report's held-completion evidence is historical. This pass only
revalidated the source chain and contract on the pinned revision.

Source anchors (baseline):

- `src/ui/projects.rs:35–100`: request capture, both bulk catalog callbacks,
  and separate navigation admission.
- `src/ui/chats.rs:535–546, 558–598`: Core replacement and refresh epoch guard.
- `src/ui/chats/codex.rs:44–79, 205–287`: paged discovery guard, pending-delete
  filtering, epoch increments and deletion cleanup.
- `src/ui/workspace.rs:49–56, 86–89`: distinct epoch and intention contracts.
- `src/ui/workspace.rs` / `src/ui/workspace/drivers.rs`: generic async error
  presentation is outside these successful catalog callbacks.

## Minimal proposal

`project-catalog-epoch.patch` changes only `src/ui/projects.rs`: **+30/−2 lines**.

1. Keep initial canonicalization, preference/recent handling and the existing
   cached Codex fast path in `open_project`.
2. Move the read-only transport section to `request_project_catalog`, which
   retains canonical project, selected driver and original navigation generation,
   and captures the current catalog epoch for that read.
3. In both success callbacks, reject an obsolete epoch **before** Core replacement
   (including `session_projects` cleanup/context emission) or Codex row mutation.
4. If the original navigation is still current, request fresh catalog data using
   that same read-only helper. Do not call `open_project`/`begin_navigation` again,
   do not use a stale local Codex shortcut, and do not replay a creation operation.
5. If navigation is obsolete too, stop. If the epoch is current but navigation
   is obsolete, retain the existing useful metadata merge and let the existing
   final navigation guard reject only selection.

The practical simplification is one retry entry point shared by both drivers,
not a reduction in LOC. It makes read recovery distinct from initiating a new
user action. The six-line admission checks remain next to each transport's
different mutation; introducing a generic callback framework merely to remove
those lines is not justified. No new field, dependency, protocol, persisted
state, or UI control is introduced.

## Deliberately limited guarantee

The proposal closes **obsolete-generation admission in successful project
discovery callbacks**. It is not a universal deletion/catalog fix.

- A read begun after delete-start but before delete-finish can be epoch-current
  and still contain a `deleting_sessions` row. Normal Codex paging filters that
  set separately; project merge/selection does not. This behavior is unchanged.
  No new session is deliberately created merely because pending rows are filtered.
- Core `start_chat`/`new_session` callbacks also carry a full catalog alongside an
  acknowledged creation. Their separate admission gap remains open. Dropping or
  retrying those entire callbacks would lose acknowledgements or duplicate effects;
  this proposal does neither and does not claim those paths fixed.
- Existing Codex creation/resume metadata, startup restoration, unrelated catalog
  writers, snapshot ordering within one epoch, and transport connection identity
  are not generalized into this policy.
- Retry reads retain the captured driver, but the unchanged empty-catalog Core
  fallback `new_chat_in` can consult current preferences. No new whole-operation
  driver-binding guarantee is claimed.
- Generic transport errors are still reported by existing `call_in` /
  `call_codex_in`; the new epoch guard covers their successful data callbacks only.
- Further epoch changes can cause further serial reads while the intention stays
  current. This adds work under churn and does not guarantee bounded completion.
  A retry captures a new epoch, and another newer navigation can stop its next
  retry. No parallel retry fanout is introduced by this success path.

## Verification and proposed controls

**Actual:** source inspection, fresh ref checks, exact Git blob comparison,
whitespace check, patch application/byte comparison, and independent source review.
Rust/Cargo/rustfmt are absent in PATH. No installation was attempted.

`regression/template.rs` proposes seven std-only Rust callback-queue test cases;
six iterate both drivers. `regression/generate.py` only extracts selected full
production functions, records their hashes, and generates baseline/candidate
Rust source. Visibility and the `OpenDocument` module path are the only textual
adaptations to those function bodies. It is not a Rust parser or a runtime test.

Proposed coverage:

1. Obsolete epoch plus obsolete navigation: no metadata mutation or retry.
2. Obsolete epoch plus current navigation: exactly one read retry, same project
   and driver despite changed preferences, no new navigation, bypass cached path.
3. Current epoch plus obsolete navigation: merge metadata without selection.
4. Current epoch plus current navigation: normal selection.
5. Repeated epoch changes: one queued read at a time until stable delivery.
6. Fresh empty retry: invoke the existing creation fallback only after admission.
7. Existing cached Codex fast path: no catalog read.

**All seven Rust cases are NOT RUN, including baseline.** There is no red/green
runtime result. The harness substitutes GPUI/window/context, DTO conversion,
transport, open-chat and creation boundaries; it only targets the extracted
success callback control flow. It does not emulate actual deletion, driver
process scheduling, focus, backend creation, or native UI delivery. Even passing
this synthetic harness later would not replace Desktop compilation/focused UI
tests and a native window check required by `BUILDING.md`.

Suggested later checks, when the existing toolchain is available:

```sh
python3 -I -B -S regression/generate.py
rustc --edition 2024 --test regression/generated/baseline.rs -o regression/baseline-tests
rustc --edition 2024 --test regression/generated/candidate.rs -o regression/candidate-tests
regression/baseline-tests
regression/candidate-tests
```

These commands were not executed except the explicitly recorded text generator.
Do not describe the candidate as production-ready, compiled, or PN-1 runtime-fixed.
