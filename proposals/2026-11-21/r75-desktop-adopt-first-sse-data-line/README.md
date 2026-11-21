# Reuse the first Desktop SSE payload line rather than copying it

**Verified in the R75 focused headless gate.** One Desktop production change. Same source patch applies at exact pin `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and sealed M150 plus Desktop #393, #396 and #398. Four exact compiler-provenance parser runs; no native, socket-transport, timing, RSS, or remote work.

## Verified repeated source path

Pinned Core's `app_server/http/sse.rs::encode_sse_output` writes one compact JSON payload into `event: output\ndata: ...\n\n` for initial/replacement snapshots and ordinary broadcast events. Payload text newlines are JSON-escaped. Desktop workspace cold startup and usual chat creation both call `connection::spawn_pump`; each initialized Core chat has its own receiving pump and reconnect reuses that reader implementation. In `src/api/mod.rs::EventStream::next`, `read_line` already allocates and fills the whole input line. For the ordinary one-data-line frame Desktop then copies the complete payload to its separate accumulator before handing it to the parser.

Retain the first nonempty payload line's existing allocation and store the exact UTF-8 slice start. If the scratch String capacity is already more than twice that line length, retain the old copy path so a small payload does not pin a large scratch allocation and force another one. Parse that slice after the same blank-separator read. This is not a shared cross-chat event cache, and does not reuse buffers across events. The moved scratch buffer may now allocate for smaller following lines, and multiline growth may differ; the oversize guard addresses disproportionate reuse, not every capacity pattern; the claim is specifically removal of the explicit first payload byte copy, not fewer total allocator calls.

## Exact framing shape

- Before an effective nonempty data line, both versions keep the assembled payload empty. A sole ASCII separator space after `data:` is removed exactly once, and empty segments before payload do not suppress heartbeats.
- Thereafter the candidate's suffix is the original accumulated payload. Its offset is a UTF-8 byte index taken from the same trimmed slice. Each continuation still contributes the same newline and exact bytes. Read-line errors, invalid UTF-8, comments, ignored fields, CRLF trimming, partial final frame at EOF and blank-separator timing are unchanged. The JSON parser and reconnect, timeout, channel, event order and controls are not changed.
- Distinct from Core #355, which shares only server-side catalog notification bytes. No changes to #398 summary ownership, #396 history text sharing, #393 cardinality trim, or the prior Desktop source stack. Exact pin and sealed pre-#398 `src/api/mod.rs` have equal SHA `5d4c23ce9e43e23672847d231a01d431caeb3e182441cb6ecb4886a1b3b1b537`; #398 does not touch it.

## Executed focused proof

The run compiled the exact Desktop parser plus a temporary count only at explicit String payload-append calls and capacity checkpoints. The **Core-pinned encoder function** was extracted unchanged from its pinned archive and compiled with its exact Core-locked `bytes 1.11.1`; all other 125 fixture identities are from the pinned Desktop lock, including contracts `7cbc7206f03fac130d05bed2844de275476fedc8`. The two distinct synthetic Core session transcripts each include a 50-row Unicode/escaped snapshot and 32 runtime deltas. Controls include fragmented multiline/CRLF, leading empty data and an empty continuation, heartbeat/comment/ignored field, JSON whitespace-only, invalid UTF-8, an injected read failure, EOF without separator, and response/error variants.

| Executed fixture | Explicit UTF-8 payload bytes appended to accumulator, baseline → candidate |
|---|---:|
| Cold snapshot + 32 deltas, chat 1 | 88,386 → 0 |
| Cold snapshot + 32 deltas, chat 2 | 88,386 → 0 |
| Multiline control | 589 → 588 |
| Small payload between two benign 128 KiB ignored fields | 444 → 444 (stock scratch fallback) |

The latter control sampled exactly 262,588 bytes of simultaneous accumulator + scratch String capacity in both arms. This is logical capacity sampled immediately after successful line reads, **not** allocator/RSS peak. It shows the guarded fallback does not retain a second oversized scratch in this tested scenario. No general allocator-call reduction is claimed, and BufRead and JSON parser copies are excluded from the explicit append ledger.

All decoded result traces were byte-identical within and across both exact source tiers, with common SHA `72c347c11b8ebf54fa81bf70c4791587a981117b73d60fe7d6516f393a7efa34`. The candidate was compiled as a fresh, exact non-test binary per arm; verified the executable before/after SHA and embedded arm, versions/inputs in `cargo-provenance.json`. The authoritatively parsed frames ran headlessly from synthetic sources; no actual HTTP connection, reconnect loop, UI or latency/RSS test.

## Reproduce

Use the pinned, sealed inputs and warmed existing offline build lane. Reserve at least 512 MiB free and coordinate at a maximum +200 MiB growth; the original gate held the shared exclusive lock, one offline locked build job, and stayed below the limit. Set absolute `CARGO_HOME` and `CARGO_TARGET_DIR` for runtime.

    bash verify.sh --prepare PINNED_DESKTOP_GIT SEALED_M150_DESKTOP SOURCE_SEAL PATCH_393 CUMULATIVE_PATCH_396 PATCH_398 PINNED_CORE_ARCHIVE
    bash verify.sh --run PINNED_DESKTOP_GIT SEALED_M150_DESKTOP SOURCE_SEAL PATCH_393 CUMULATIVE_PATCH_396 PATCH_398 PINNED_CORE_ARCHIVE
