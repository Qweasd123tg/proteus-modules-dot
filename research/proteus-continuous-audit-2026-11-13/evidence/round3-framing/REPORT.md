# Proteus cross-repository functional contract review

## Revisions

The four origin/main heads were rechecked with git ls-remote during this review and matched local HEAD:

- Proteus-harness/Proteus-core: `89997df995df7c39b713e16aba216ecb19c8f497`
- Proteus-harness/Proteus-modules: `3270dc0f894eaf4d0360306052b806099b8f5351`
- Proteus-harness/Proteus-desktop: `75bf201764278eac4b50d156650edcf1429101ff`
- Proteus-harness/Proteus-desktop-extensions: `4df3d0f7c168aa2947a5b014cf02f92984499d3f`

No production source was edited or published. The Extensions checkout already contained another auditor's changes to sdk/src/host/tests.rs; those tests are not compiled by the non-test SDK dependency used in this probe.

## Confirmed new finding: P3, inconsistent JSONL frame-size contract

Desktop counts the compact JSON body against 16 MiB, then adds LF without checking the resulting length. SDK stdin framing counts LF against that same 16 MiB maximum. Therefore a legitimate render envelope of exactly 16,777,216 JSON bytes is admitted by Desktop but terminates the SDK reader, and the render callback never runs. At 16,777,215 JSON bytes it succeeds; at 16,777,217 Desktop rejects it before sending.

Locations:
- Desktop src/declarative/process/io.rs:80-105, especially <= MAX_FRAME and count.0+1.
- Extensions sdk/src/host/inbox.rs:77-88; start():97-103 terminates its loop on the mismatch.

Core independently has the same convention mismatch in its process-host abstraction: writer.rs:430-437 checks JSON-body bytes, while framing.rs:57-65 includes LF. A real ProcessTransport<NewlineJsonFraming> round trip through /bin/cat accepts send_frame at exactly the configured limit, then receives ReaderStopped for that very frame. This is a generic transport repro, not a claim that a current stock module emits this exact size in typical operation.

Verified cases in boundary.log:
- Core limit32, JSON31 => send+receive success.
- Core limit32, JSON32 => send success, receive ReaderStopped.
- Core limit32, JSON33 => sender FrameTooLarge.
- Core default8MiB, JSON8MiB-1 => success.
- Core default8MiB, JSON8MiB => send success, receive ReaderStopped.
- Core default8MiB, JSON8MiB+1 => sender FrameTooLarge.
- Desktop16MiB-1 => admitted and actual SDK process produces probe_ack.
- Desktop16MiB => admitted but actual SDK process reports extension input frame exceeds 16 MiB; no ack.
- Desktop16MiB+1 => rejected by Desktop's admission code.

Method: probe/src/main.rs links unchanged Core process-host and Extensions SDK production code. It imports Desktop io.rs and budget.rs unchanged. Desktop's Outgoing is substituted with serde_json::Value containing a protocol-valid render/content envelope, and unused receiving-side State is supplied; this is NOT a full GPUI/desktop process-launch test. SDK run() is unmodified and runs as a subprocess with a minimal synthetic Extension implementation. Fixtures contain only synthetic strings. No service, live session or user data is used.

Recommended fix: choose one convention explicitly and align sender/receiver admission. Existing Core parser tests explicitly assert that the delimiter is part of its limit, so changing only the receiver would alter a tested contract. Add sender-to-receiver limit-1/limit/limit+1 round-trip tests, including the real Desktop/SDK pair. Core's protocol-neutral writer must account for the selected framing instead of blindly subtracting one byte for Content-Length framing too.

## Test results and negative checks

- All 9 boundary scenarios above passed as defect-characterization checks.
- Existing Core `cargo test --offline -p proteus-process-host --lib framing`: 8 passed, 25 filtered out. These include reader equivalence/chunk-boundary tests and a deliberate LF-inclusive-limit test. They do not validate writer-to-reader compatibility.
- All 13 production extension manifests use protocol4 and require only features included in Desktop's 36 advertised features (manifest-compat.log).
- Desktop's pinned Core5e8b6ae app_protocol DTO source is identical to current89997. In proteus-contracts as a whole, only ModelLimits default and shaper tests differ. The pin alone is not a proven HTTP contract bug.
- Modules' pinned Coreb5fac84 proteus-contracts source is identical to current89997.

## Source review coverage

Read relevant DTOs and synchronization paths: Desktop api/mod.rs, api/transport.rs, connection.rs; client-common pending.rs, sync.rs, response.rs, session_selection.rs; declarative process.rs, process/io.rs, process/budget.rs, session.rs; runtime commands.rs/scopes.rs and host/scope.rs; SDK host.rs (routing, render, API, polling and context routines; not every helper), host/scopes.rs and host/inbox.rs, conversation.rs, preferences.rs, analytics.rs, format.rs; Core SSE implementation and conversation/user-input endpoints/contracts. Also read Desktop user-input/question-card implementation and selected projection event definitions; reviewed protocol Outgoing definitions and extension protocol documentation through session messages. Read full Core framing.rs plus its reader tests and writer admission code, not every process-host function. Performed contract tree comparisons against both dependency pins.

Not a full line-by-line audit of all repositories. No native GUI run, provider-network test, real module8MiB response, actual Core HTTP server test or publication performed. Other auditors cover component-specific behavior.

Additional unconfirmed test gap: SDK Host::call uses ureq read_to_string's default10MiB response limit, whereas conversation() is documented as full canonical history. No production extension currently calls conversation(); large-history reachability/end-to-end behavior was not tested, so this is not promoted to a second finding.

## Reproduce

```sh
source /workspace/shared/proteus-toolchain/env.sh
CARGO_TARGET_DIR=/workspace/shared/cross-repo-review-evidence/target \
  cargo run --offline --manifest-path /workspace/shared/cross-repo-review-evidence/probe/Cargo.toml
cargo test --offline -p proteus-process-host \
  --manifest-path /workspace/shared/proteus-review-20261112/core/Cargo.toml --lib framing
```
