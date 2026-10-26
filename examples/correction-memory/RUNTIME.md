# Raw-compatible CAS runtime gate (authored; not yet run)

The phase1 hosted run [40297080188](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40297080188)
resolved a lock without compilation. The reviewed lock SHA256 is
`2b319cbe3ec46e35906574563eef2af4623e16d946665d03574480704dcbd2ea`:156packages,
retaining141 evidence-spans package identities plus15 additions. SDK3f,
rusqlite0.33.0/bundled libsqlite3-sys0.31.0 and ring0.17.14 are unchanged.
The two changed overlapping dependency strings merely disambiguate existing
hashbrown/foldhash versions. No original pin was relaxed.

This second phase replaces the lock-resolution-only workflow with a runtime
workflow. It fetches only with the committed lock and then uses offline/locked
metadata, all-target build, seven explicit test targets and the own demonstration
binary. It never regenerates the lock or invokes upstream suites. All69 authored
Rust tests remain unrun until this exact phase succeeds:4 actual-module,5 bounds,
21 evidence-contract,7 raw-argument,17 storage,7 wire and8 workflow tests. Of seven
wire cases, six use the own binary and one is a pure framing helper.

Separately,35 controller mocks,37 synthetic validator controls and six fixed live
supervisor controls precede Rust. Live controls are copied unchanged from the
usage gate; this new execution still needs its own evidence. The wait-failure
case is injected at the adapter with a real child, not a natural kernel failure.
No general descendant-settlement result is inferred. Production admission needs
8GiB initial free space, monitors the1GiB+128MiB stop threshold and uses a
1800-second outer deadline. The fresh TMPDIR/target/evidence paths share the
workspace filesystem. Limits are sampled monitors, not quotas or a sandbox.

The exact typed demonstration checks independent modules with authored callbacks
and one newly created temporary artifact: prepare two proposals, applied revision1,
durable stale conflict, identical replay without a new callback, changed-payload
refusal and readback. It independently reconstructs all fields and typed-record
hashes; generated instance/cwd/call IDs are correlated, not authenticated.
SQLite handles are not retained across evidence execution. Postcommit response
loss remains uncertain, recovered by the same operation ID and payload. An old
backup restore can erase operation history; no exactly-once claim is made.

The gate records both module/example binary hashes before and after runtime,
complete CAS+spans source hashes, exact commands, all target names/counts and full
resolved dependency metadata with bundled SQLite features. Only bounded logs and
hash receipts are uploaded, not executable binaries or user databases.
No Core authorization, official reader, live model, journal or semantic-truth
claim is made. The original source-review files are historical snapshots.
