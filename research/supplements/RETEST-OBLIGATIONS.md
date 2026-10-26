# Portability and retest obligations

This is a preparation checklist, **not an executable build/run recipe**. No source
is copied or adapted by this index. Proposed directories are not live public
artifacts. The local staging map is excluded from the public-facing payload.

## Three identities that must remain separate

1. **Historical source and executable:** keep the accepted source snapshot,
   original module/dependency pins, local binary/Node SHA256, corpus and artifact
   digests, and later review receipt. Hashes are byte identifiers, not signatures,
   permission grants, proof of semantic equivalence or proof against replacement.
2. **Trusted new build:** an operator/reviewer explicitly selects and verifies the
   repository commit, required files/locks, dependency pin, build recipe,
   toolchain/platform and isolated build destination. Record the actual command,
   outcome and produced executable hash as a new provenance chain. This step is
   not authorized or executed by this mapping. A different hash is not itself a
   bug; an unknown build is not trusted just because its hash is now known.
3. **New test execution:** bind the reviewed adapted harness and immutable corpus
   to that specific build record. A reviewer must approve the changed pin table
   before the harness can execute it. Preserve exact pass/error/outcome checks,
   process ownership, resource caps and post-run input identities. Record and
   independently inspect new transcripts before making a new runtime claim.

There must be **no accept-current-binary mode, automatic expected-hash update,
ignore-mismatch switch, build-on-pin-failure fallback or reuse of a stale runtime
receipt**. If a trusted rebuild is unavailable, a sanitized historical summary
can remain useful; a runnable portability claim cannot be substituted for it.

## Required adaptation/retest matrix

| Candidate | Preserve and review | Minimum separate rerun obligations |
|---|---|---|
| Pi | Source/lock mapping, exact ReadOnly/advisory fields, independent permutation oracle, strict outer/inner JSON, generation/sequence and raw-argument controls; retain README-only provenance resolution. | 27 harness controls; exactly 4,086 tool requests + initialize/list; all 4,013 successes and 73 intended failures; ordered actual-input readback and direct-child cleanup. |
| Letta | Full nine-file baseline mapping; v4 context-provider/ordered-many on protocol v3; finite oracle and 512-RPC per-worker bound; no callback support or persistence added. | 26 pure + 8 mocked transport controls and explicit 512 boundary; 98 workers / 398 requests / 392 responses, all 295 projections, four exact request errors, null catalog, six exact factory failures; check no response using the actual complete stdout observation, not EOF alone. |
| Hermes v1 | Corrected snapshot only; each worker initializes with sequence 0 in its own generation (8–12 historically). Preserve message-index/occurrence oracle, exact nudge text, v1 trust limits and existing continuation semantics. | 39 controls; 909 hook cases + 5 init; exact 101/793/15 outcomes, all actual-input semantics and raw frame offsets; do not reuse the superseded unrun initialization candidate. |
| Claude | Exact adapter/JS SDK imports, closed exec-only fixture argv/mode/path allowlist, clean Node/controller environment, strict DTOs and exact parser diagnostics. A Node change may legitimately change SyntaxError text and needs explicit review, not a generic-error relaxation. | 25 pure Node + 13 Python controls; 51 cases / 48 invocations; exact 52 frames / 41 ready / 37 completed / 18 error records. Repeat exact/+1 output limits with completed-write controls, ready-before-timeout/cancel and paired delayed-marker success; refuse unknown cleanup/unsettled work. |
| Catalog delta | Original commit/catalog bytes; 90 IDs/order/entry digests and 28 exact claim fragments; three disposition dimensions; 44 rejected IDs/aggregate and six shortcut aggregate; all 83 accepted reference identities and 16 evidence-layer descriptions. | Documentation/JSON/link/pin/claim review only. Adapting paths is not a runtime rerun. If referenced reports are not published, mark that explicitly; do not create fictional links or silently upgrade their evidence layers. Any newly edited claim needs its own source/evidence review. |

The counts above describe the minimum preserved historical corpus, not permission
to run now and not exhaustive coverage of all possible behavior. Future baseline
Rust or adapter tests belong to the new build's validation record and must not be
assumed from old results or silently summed with these probes.

## Resource, lifecycle and publication gates

- Keep isolated, unoptimized Python where assertions are active, strict bounded
  framing, finite invocation inventories, clean environments, owned temporary
  directories, exact expected diagnostics and pre/post source checks.
- Recalculate aggregate payload **and allocated-block** budgets for the actual
  destination. Serialize runtime reservations and check fresh free space before
  admission, preserving the configured reserve. Historical timings are diagnostics,
  not throughput, SLA or benchmark claims.
- Preserve Pi/Letta/Hermes direct-child cleanup scope. Do not generalize their
  helper to Claude's SDK-owned child groups. Unknown cleanup or denied execution
  stops the batch; an alternate execution route is not a remedy.
- Do not publish absolute local paths, environment credentials, private task
  authorization, raw process/PID directories, or the full working-tree reports by
  wildcard. Inspect the explicitly allowlisted documentation/source mapping.
  Raw transcripts stay in place in this preparation batch.
- If a future sanitized receipt or adapted source differs from a historical file,
  give it a new hash and an explicit `derived_from` relationship; never replace
  the old hash with a new file while retaining the old acceptance claim.
- The catalog's current local EVIDENCE registry is **not drop-in public data**.
  A public version must map each retained hash to an approved published report or
  explicitly unavailable evidence identity, retaining layer/pin qualifiers.
- Documentation-only publication review does not imply adapted-code runtime
  acceptance. No automatic publication or build action is provided here.
