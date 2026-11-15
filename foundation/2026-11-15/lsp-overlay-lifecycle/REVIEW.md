# Independent source review: MOD-R4-01 lifecycle options

## Verdict

HOLD close-only candidate, not the known finding and not all possible fixes. Balanced didOpen/didClose is a meaningful ownership correction, but with the present diagnostic acceptance rule it introduces an unresolved close/reopen attribution path. No implementation or runtime was performed in this review.

## Independently checked boundary

Modules c035142558f0fca43e9772fc0e50ca293abf1531: client.rs synchronizes only the requested document, remembers every successful URI/version, and resets the map on process generation change or invocation failure. There is no didClose. lib.rs serializes workspace access, but this does not serialize the server's asynchronous notifications with later invocation boundaries. The requested document snapshot is loaded before obtaining the workspace lock; no design here should promise a transactionally current filesystem snapshot.

parse_publish_diagnostics rejects another URI and versions below the requested version. Missing/null versions are accepted; versions above the requested version are also accepted. The returned document_version is the client's expected value, not proof of the notification's origin. wait_for_diagnostics returns latest after a receive timeout of at most 100ms, or at its deadline. This is a published snapshot, not a compiler-completion barrier.

## Close-only counter-schedule

1. Invocation A receives diagnostics for URI U, sends didClose(U), returns.
2. Invocation B drains its auxiliary notification buffer and sends didOpen(U, version+1).
3. An unversioned empty diagnostic publication associated with the previous close arrives after that drain.
4. It matches U and is accepted. If no replacement arrives before the next receive timeout, B returns a clean report attributed to its new document_version.

Keeping monotonic versions rejects an explicitly old version, but cannot identify an unversioned publication. Sending close before returning is not acknowledging server processing. An extra drain or fixed quiet interval cannot prove absence of a later publication. Ignoring all empty publications would instead lose genuine clean results.

This is a permitted notification-shape/design counterexample, NOT a new reproduced rust-analyzer incident. Existing protocol tests cover same-document didOpen/didChange and generation reset, not this schedule; no tests were executed. Historical mock results remain historical evidence only.

The official LSP3.17 didClose specification transfers content ownership back to the URI. publishDiagnostics specifies an optional version and server-owned replacement publications, including empty arrays. Advertising versionSupport states client capability, not a promise that every server publication contains a version. Nor does LSP require every project-language close to clear diagnostics.

Sources: https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/textDocument/didClose.md and https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/language/publishDiagnostics.md (read directly; mutable upstream documentation, not pinned RA behavior).

## Coherent alternatives and costs

- A new process generation for each invocation prevents contamination by prior invocation overlays/notifications, using existing reset/session mechanisms. This is a plausible narrow alternative, not impossible and not a new framework. It abandons the advertised persistent-process/cache benefit and incurs repeated initialization/indexing; it still does not make the first publication final compiler output or freeze concurrent disk edits. Cost and behavior must be selected explicitly before a patch.
- Balanced close/reopen plus acceptance only of the exact requested version provides an attribution rule for correctly versioned servers. Unversioned results must then remain unavailable/timeout rather than silently becoming clean. This is a compatibility change, not a transparent fix; real server behavior must be established. Even exact target version is not an acknowledgment that all dependency work has completed.
- Refresh all retained overlays from disk before target synchronization preserves persistent ownership, but needs selected behavior for deleted/unreadable/non-UTF8 files, version updates, and partial refresh failures. It incurs work proportional to retained documents. Existing host reset can bound a failed synchronization, but this option does not by itself fix generic unversioned notification attribution or establish a multi-file atomic snapshot.
- Keeping only one open document still closes/reopens documents and does not remove the same-URI late-notification question.

Therefore do not publish simple balanced-close code as an unqualified fix. Conversely do not claim that correctness requires a new shared DTO/framework or that every bounded fix is impossible. Select process-isolation cost, stricter publication compatibility, or explicit refresh semantics first. A later candidate needs two-file new-error/removed-error cases plus delayed old/unversioned close publications and same-URI reopen controls; proposed tests would not count as passing until actually run.

## Read identity and limits

Own SHA256 checks:
- client.rs: adb625f38a156c658ed7ef192f730218d4cf03dfb76e17076b1c2f6816727700
- diagnostics.rs: a8ebc5a7d93e6d56e07e45e175bb4fa1267126ade7811bb954ee24745cf9fa97
- lib.rs: d74fcd6f54dba0b95141389a108819457b1bffb8f9e8fedeb5c033e87563e4d4
- tests/protocol.rs: adb38c19304c7fedbc456c3ac2a813a34f5a993e204e62d9d04b7f162a0e82be

Initial source catalog/fresh refs are research evidence. Reviewed lifecycle/diagnostic portions only. No Rust, compiler, mock server, SQL, project script, or live server execution; no production changes. This review predates the docs-only publication.

## Addendum: actual pinned notification drain

Independently read Core pin 41bdfffa6e70228278b4abc758b7f81a12672f35 session.rs, Git blob b6a5aea13cf78de84d6c039aba22470f901f245c (catalog identity), own SHA256 8c0d792cd1cf0488d8961928655a6a45d19f1dcd458a7447ba3d897eea7d653c. Lines118–122 drain only the session's auxiliary notifications Vec. recv_response/wait_notification can populate it; recv_frame delegates through recv_buffered_frame to transport (lines71–76,204–209), not to this Vec. Thus the invocation's drain does not even promise removal of already queued transport frames, much less a server-processing barrier. The counter-schedule above now says auxiliary buffer explicitly. This strengthens the same design limitation; it is not a separate new finding or runtime result. Verdict unchanged.

## Final coordinator report review

Read the original research report in full; own SHA256 d0051ae1b6540e50532a3cf2b807525b6d95dc0d2b0c08d9fb9c3b06d44c74d3 matches the supplied final report. No blocking overclaim found. It keeps the close-only counter-schedule distinct from deployed rust-analyzer incidence, limits snapshot/completion claims, describes the actual auxiliary-buffer drain, and leaves the known finding open. Alternatives state their compatibility/cache/error-policy costs rather than silently selecting a changed contract. The source catalog now contains eight exact blobs according to source-byte verification (six Modules tool sources plus root Cargo and actual-pin Core session); this supersedes the earlier six-blob catalog note, not the independently listed file hashes. No additional runtime or tests were performed.
