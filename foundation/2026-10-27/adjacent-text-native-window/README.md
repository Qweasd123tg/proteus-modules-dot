# Native-window streaming gate (isolated qualification, not production code)

This experiment adds no Desktop/Core changes. A fresh same-job portable-fast build reconstructs
the exact PR28 source composition already qualified by PR30, then launches its **actual packaged
native binary** on an authenticated Xvfb X11 display with Openbox and Mesa software rendering.
A deterministic localhost HTTP/SSE fixture replaces only the app-server transport. No real model,
API key, user session, external tool execution, or paid provider is needed.

## Provenance and workflow

- Desktop base: 2bf38f67055f10f5ed0fd225399ba77d84756ba1.
- Reviewed PR28: 88872cb2e3befbff4cfeaff4919b1dc9675195b1.
- Reconstructed candidate: commit ac1b176f79a4f5706520c4f68a1bcb1783b08f69,
  full tree b30533cb589c30b8ca843f0b8d05164e3a02b5b4.
- Original PR30 qualifier: cc69f8140c8cc9966356e7152b3a47594f672a65.
  Prior portable run: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40437630201.
- Prior canonical Desktop semantic proof (232 tests), not re-executed by this gate:
  https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40432288991.

The workflow accepts only the exact branch ci/adjacent-text-native-window-20261027 in
Qweasd123tg/proteus-modules-dot. Reviewed push is the normal trigger; dispatch is optional.
It uses contents:read, pinned actions, no persisted checkout credentials, no caches or binary artifacts.
The copied PR30 runner is **adapted**, not byte-identical: its constructed environment adds
npm_config_audit=false and records that value. Its private copied self-manifest hash is refreshed.
The adapter verifies all original PR30 hashes and limits changed paths to that runner/manifest.
This prevents an unauthorized automatic npm Bulk Advisory POST; it is NOT an advisory audit.
Product sources, locks, build scripts and qualified dependency graph remain unchanged.
A fresh binary hash is bound to the same-job inventory before and after native tests; no equality
to the unavailable PR30 binary bytes is claimed.

## Stages and externally visible assertions

1. **Initial feasibility gate:** exact native PID/class/title, mapped/viewable client window and
   geometry; real OCR-visible fixture text, actual typed composer request, rendered streaming delta.
   Failure here stops later scenarios. A headless GPUI TestWindow or nonblank image cannot pass.
2. **Delta/UTF-8 oracle:** render initial text, then a UTF-8-byte-offset tail correction.
   A ToolCallRequested barrier stops streaming without replacing accumulated text. Hover the exact
   visible assistant row, localize the revealed Copy control, require its Russian tooltip, install
   a distinct external CLIPBOARD nonce, click the native control, and read exact UTF-8 externally.
   Owner transition, changed localized control pixels, source-row PNG and timing are retained.
   The expected result is never preloaded into CLIPBOARD. Any same-row completion or replacement
   snapshot before this read invalidates the oracle, since completion could heal lost deltas.
3. **Non-text barrier:** same-message continuation stays on the original final marker line and
   before the tool marker; a distinct later
   message appears after it. Semantic screenshot markers establish visible order.
4. **Scroll anchor:** actual wheel scroll exposes one unique anchor and a mutable row below it.
   Each staged mutation and later FIFO acknowledgement must keep the client-relative anchor within
   two pixels. Offscreen appends precede the visible acknowledgement. Wheel-to-end resumes following;
   an ungated bounded 32-delta multi-paragraph burst must expose its new tail without further input.
5. **Cancellation twice:** actual Stop must POST the current run/session. A distinct unsent draft
   entered after send must survive pending and terminal stages. Stop remains while the fixture
   reports pending cancellation, with a later text acknowledgement, then disappears after
   terminal active=null. This observes server-pending retention, not internal CancelRequested state.

Blank lines deliberately produce separate plain-text paragraphs; no code-fence Copy ambiguity.
Strict marker uniqueness/confidence, fixed DPI/geometry and source-defined control localization
replace font-fragile full-image equality. Every required stage retains its full PNG, SHA256,
OCR TSV/boxes/confidence, input sequence, monotonic timestamp and window metadata. Protocol
trace records sequence and enqueue/write receipts, but **write boundaries are not client batch boundaries**.

## Bounds, evidence and human review

The native controller has a 600-second active-work deadline plus bounded cleanup (the whole native
step has a 12-minute hard limit), stages normally 15 seconds, 4096 utility commands,
1024 fixture requests, 8192 protocol trace records and 4096 queued SSE events. At most 40 PNGs /
32 MiB are retained (one frame / 5 MiB reserved for failure), complete background logs at 2 MiB,
and native JSON at 8 MiB. Overflow is failure, never truncation-to-PASS. Process groups and
fixture handlers are tracked through bounded cleanup. Synthetic negative tests reject stale or
wrong-client frames, absent/duplicate markers, preloaded clipboard, healing completion,
wrong cancellation IDs, observed renderer errors, missing scenarios/receipts and bad provenance;
process controls exercise timeout/output/orphan/signal ownership paths. These are harness controls,
**not compiled application mutation coverage**.

The upload allowlist contains only synthetic screenshots/logs/results and bounded portable receipts;
never binaries, runtime homes, tokens, Xauthority, caches or user data. Retention is seven days.
Hard runner/job termination can prevent final evidence upload; missing evidence is inconclusive.
A human must inspect first-run full client PNGs and receipts before calling this gate qualified.
OCR/control ambiguity, unsupported GPU/window startup, or missing evidence is FAILURE/INCONCLUSIVE,
never retry-until-green or skipped PASS. The first hosted run qualifies feasibility itself.

## Security and limits

Only apt package installation uses sudo; rustup and all build/native steps run as the normal user.
The native controller refuses UID 0. It makes no AppArmor/sysctl/userns/security-policy
changes. The isolated display uses a synthetic cookie and disables TCP; the fixture binds loopback
and requires a synthetic bearer token. Fresh per-case HOME/XDG/config/workspace/session paths and
the supported empty extensions override exclude real data and extension subprocesses. Environment
construction omits provider credentials, proxies and inherited user configuration.

No installed Rust log backend is verified in the unchanged product binary:
rust_log_backend_initialized=false; renderer_diagnostics_complete=false. Captured stdout/stderr
errors are rejected, but silence is not proof of absence of renderer/device-loss diagnostics.
No hardware/Wayland coverage, real Core cancellation, bundled-extension UX, every-frame stability,
internal ListState identity, actual coalescer invocation/batch count, performance/RSS/allocation,
bit reproducibility, release archive or merge-readiness claim is made. Software GPU recovery may
differ from initial startup. Apt/runner/font versions are recorded rather than pinned.
Native utilities use Ubuntu /usr/bin/python3 for apt Pillow; the build retains Python 3.12.15.

Primary source references:
- https://github.com/Proteus-harness/Proteus-desktop/tree/2bf38f67055f10f5ed0fd225399ba77d84756ba1
- https://github.com/Qweasd123tg/proteus-modules-dot/pull/28
- https://github.com/longbridge/gpui-fast/tree/07b42ebf1f43088b8b74a7d4fca6b95e44e04265
- https://sources.debian.org/src/xclip/0.13-4/xclip.1
