# LSP overlay lifecycle follow-up: HOLD close-only proposal

## Decision and scope

No patch and no new finding in this pass. The existing MOD-R4-01 stale-overlay finding remains open. A balanced didOpen/didClose change is attractive, but is not yet a contract-preserving fix when composed with the current optional-version diagnostic reader. Independent source review agrees with HOLD for that option, not with a claim that all fixes are impossible.

This is a source/design review only. No Rust, compiler, mock server, rust-analyzer, project script, or application runtime was run. Historical protocol-mock evidence in [the prior MOD-R4-01 report](../../../research/proteus-continuous-audit-2026-11-13/evidence/round4-lsp/REPORT.md) was produced on older source and is not a regression run for this pass. This documentation publication contains no source modifications, production changes, new severity, or new incidence claim.

Start and end refs agree:
- Modules: c035142558f0fca43e9772fc0e50ca293abf1531.
- Core main: bcbda4435534a296c707a1daa250813d692f68e1.
- Actual Modules Core dependency: 41bdfffa6e70228278b4abc758b7f81a12672f35, verified in Modules/Cargo.toml. ProcessSession below is read at this pin, not substituted from main.
- Delivery repository: a5af61cfa8f26292559d6fcde69b9983684f601a, including PR122. PR122 root-view projection has no direct lifecycle fix here and remains an uncompiled candidate with its own retention cost.

Eight exact Git blobs are catalogued and byte-verified in SOURCES.json; source snapshots are not included in this publication; only lifecycle/version/diagnostic behavior was reviewed. Filesystem authority, sandbox behavior, process security, and concurrent editing mechanisms are outside scope.

## Existing contract and common invariant

The tool's stated behavior is a persistent rust-analyzer process returning bounded publishDiagnostics output (lib.rs:101). It reads the requested document from disk, serializes access to its workspace, and updates only that document (lib.rs:74-89; client.rs:132-158). Successful calls retain each URI/version indefinitely; generation change or an invocation error clears the map (client.rs:123-131,169-179). No didClose is sent.

Thus an older successfully opened dependency is still client-owned after its disk contents change. The known multi-file failure is not a missing watcher notification: LSP makes the client responsible for open content. The useful invariant is that a disk-backed diagnostic tool must not leave old client-owned dependency snapshots active without a refresh/retirement policy. A second invariant is that publications from an earlier invocation must not silently be attributed to a later one. A local cleanup must respect both.

The current reader accepts absent/null versions and all integer versions at least the requested value (diagnostics.rs:128-138). Its report records the requested version separately from the publication version. After any accepted target publication, a receive timeout of up to 100ms returns the latest report; the total deadline also returns the latest if present (client.rs:199-223). This is a published snapshot, not proof that all workspace analysis completed.

## Why close-only is not ready

A possible sequence, not a reproduced stock rust-analyzer incident:

1. Call A receives a report for U, then the proposed code sends didClose(U).
2. Call B drains the auxiliary notification buffer and sends didOpen(U) with a higher version.
3. An unversioned empty publication associated with the earlier close arrives after that drain.
4. It matches U, is accepted, and can be returned as clean after the next receive timeout before replacement diagnostics arrive.

Retaining monotonic versions rejects an explicitly old version but cannot attribute an unversioned publication. Clearing the version map and reopening at version 1 would additionally weaken protection against old versioned publications. Keeping one open document rather than none still has close/reopen transitions when calls alternate files.

The exact pinned ProcessSession::drain_notifications (session.rs:118-123) empties only its auxiliary Vec populated by request/wait_notification paths. recv_frame reads the transport directly (69-76,204-208); drain is not even a complete transport-queue drain, much less an analysis barrier. Repeated drains or an arbitrary delay do not prove no publication will arrive later. Dropping every empty publication would lose genuine clean results.

LSP3.17 permits an omitted publication version. versionSupport advertises client capability, not a guarantee that the server always sends it. Server publications replace previous diagnostic arrays, including empty arrays. Closing transfers content ownership back to the URI; it does not require every project-language server to clear diagnostics on every close. The counterexample is about the existing accepted message shapes and ordering uncertainty, not a claim that stock rust-analyzer always follows it.

Primary references:
- [didOpen ownership](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/textDocument/didOpen.md)
- [didClose ownership](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/textDocument/didClose.md)
- [publishDiagnostics versions and replacement semantics](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/language/publishDiagnostics.md)

These upstream documentation URLs are mutable, not evidence of a deployed rust-analyzer version.

## Coherent choices, not forced abstractions

| Option | Useful guarantee | Explicit cost or unresolved contract |
|---|---|---|
| Fresh process generation each invocation using existing reset/session | Removes prior invocation overlays and frames from the next session | Loses advertised persistent cache; repeated initialization/indexing; no final-analysis or atomic-disk guarantee |
| Balanced close/reopen and exact requested-version acceptance | Attributes correctly versioned publications to the requested target version | Unversioned server results become unavailable/timeout; compatibility change needs server evidence; target version does not certify dependency completion |
| Refresh all retained overlays before target update | Keeps persistent cache and removes known stale retained content under a selected refresh policy | Work grows with retained documents; deletion, unreadable/invalid/oversized files, version updates, and partial failures need an explicit policy; no atomic multi-file snapshot or general unversioned attribution guarantee |

No generic framework or shared DTO is required merely to choose among these. Sync-all remains feasible; it was not disproved. A narrow existing-host reset can bound a refresh failure, but deciding when to return failure versus discard caches affects caller behavior. Do not silently select compatibility, persistent-cache cost, or dependency-read error semantics under the label of cleanup.

The tool does not receive or mutate user editor buffers. The requested disk snapshot is currently loaded before the workspace mutex. Concurrent external disk changes can occur after any read; none of these options promises a transactionally current workspace or should overwrite user edits.

## Proposed validation, NOT RUN

Before delivering a selected candidate:
- Two-file old/new dependency content, both newly introduced and removed diagnostics; persistent/fresh/refreshed controls.
- Same-URI repeated calls, alternating URIs, monotonic version behavior, process generation restart.
- Late explicitly old-version publication; late omitted/null-version publication; empty legitimate current publication. Verify unavailable/timeout rather than false clean if strict versions are chosen.
- Deletion/read/encoding/size failure after a successful dependency open if sync-all is chosen; partial refresh must not leave an undocumented mixed state.
- Existing same-document didOpen/didChange, idle restart, unavailable-binary controls.
- A real supported rust-analyzer integration run when the toolchain is available. A protocol mock alone does not establish deployed server incidence or performance.

These are a test plan, not implemented or passing tests. Hold the close-only patch; the known bug is not closed. The next useful step is an explicit lifecycle/compatibility choice and its bounded regression tests, rather than another syntactic refactor.
