# Reuse the attached terminal's existing canonical lookup key

The attached terminal repeatedly serializes its immutable owner chat, path and terminal descriptor to look up the same document. The current and visible guards now share one lazily computed key per viewer, using the original serializer. A failed workspace or connection check still stops before computing or consulting the key. The code does not cache the result of either guard, or substitute an input tab ID for the original canonical output.

Exact Desktop b6a7ec2d8d7e486c8aba01291aa8c89774c4cded and sealed M150 plus the 59-patch Desktop roster through #440. Only the terminal view's memo field, initialization and the existing key lookup arguments change. Inherited #415 terminal render/cursor logic is left intact. No change to parser, layout, current/visibility/entity checks, Settings, owner requirements, connection, transport, input/command behavior, window detach or rehost policy.

## Focused repeated work

One inert attached-view target, 202 canonical UTF-8 bytes including prefix, real Contracts terminal descriptor and tabs with one active visible pane. Work counts allocation/reallocation requests and total requested allocation sizes within the exact lifted guard methods:

| Guard sequence | Requests | Requested bytes |
| --- | ---: | ---: |
| Cold pair, current plus visible | 9 → 5 | 1,234 → 633 |
| 256 warmed visible + current pairs | 2,304 → 256 | 315,904 → 8,192 |
| 256 warmed current checks alone | 1,024 → 0 | 153,856 → 0 |

The visible-tab check still allocates the same pane-list scratch; the change removes only serialization/prefix assembly. A separately instrumented copy confirmed that the first qualifying guard encodes the key once, then 64 repeated guards encode it 0 instead of 64 times. The second viewer initializes its own key independently. Missing API, stale connection and failed weak owner still skip encoding; a Settings-covered but otherwise eligible first visible guard still performs its original first encode before the document predicate.

**Tradeoff:** the candidate retains one 202-byte key (capacity 202 in this fixture) per used viewer and one 24-byte inline OnceCell of String on the tested host. The lifted Remote subset was 112 → 136 bytes; this does not measure the whole native object. A viewer that never gets through the initial workspace/connection checks retains no key backing allocation. On a single eligible check there is no encoding saving, and key length varies. No wall-time, total-memory or UI latency claim.

## Parity and source evidence

Four fresh test executables (4/4 each, baseline/candidate on both tiers), plus exact source-bound tabs libraries. All four complete guard/ID records matched byte-for-byte. The headless carrier mechanically lifts the exact Target serializer/parser, guard bodies, memo construction and rehost assignment. It uses the exact active/parked membership and Settings-free visibility expressions, real tabs, and modeled weak GPUI entity and connection state. Tests cover escaped Unicode, exact key string, malformed/prefix/UUID/owner/path inputs, accepted noncanonical raw alias failing canonical membership as before, active/hidden/parked/Settings, wrong or replaced entity, stale and absent connection, dead workspace, and rehost. No native terminal, PTY, programs, commands, app-server, remote service, or actual keystrokes were started or used.

Apply/reverse/format/whitespace passed on both tiers. Same 125 pinned external identities from the existing Contracts+Tabs warm closure; one offline locked Cargo job under the common lock. The 512/256 MiB floors and +200 MiB cap were unchanged; peak observed growth 3,892 KiB target / 37,544 KiB temporary. An initial test-only diagnostic used a nonliteral assertion message and was corrected before a runtime started; product patch unchanged. The sealed Desktop tree and lock were rechecked after the successful runs.
