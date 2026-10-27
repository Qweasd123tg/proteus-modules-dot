# Session ownership and coordinated local deletion

**Experimental source candidate, not an accepted full ownership fix.** It is
based on Proteus-core commit
`63454d4e8b1e4e6b26d088fce2a17d46f30390ae`.
The initial conservative candidate at `bae05a0bc9ac7da2f6e17e5627214f762c2ffb3b`
compiled and passed its 11 focused cases, but the
[canonical full gate failed](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40438671031)
on two existing HTTP deletion tests: local Busy broke the established lifecycle.
This correction preserves those tests and adds explicit local-owner coordination.
Its new code has been parsed/formatted only; its hosted qualification is **not run
at authoring**. Each later receipt applies only to its exact commit and hashes.

## What this slice changes

- The permanent writer lease file is a sibling of the removable session
  directory: `.<10-digit-session-id>.write.lock`, under its canonical parent.
  Cooperating writers acquire it before session mkdir, metadata creation or
  recovery. The lock file is never unlinked by session deletion.
- New handles receive creation permission from the constructor's initial
  observation. Clones share that permission; first successful mkdir or observing
  an existing slot consumes it. Existing SessionStore handles never authorize their own write paths to
  recreate a missing session. This does not yet fence runtime config/image writers.
- Preflight ownership is tentative. Failed identity/materialization/recovery
  releases only a newly acquired lease, including during unwinding; a previously
  committed owner's lease is retained.
- Cold path-only deletion remains Busy for every live owner; a path cannot steal
  another runtime's lease. An explicit matching AppServerHandle instead validates
  its configured scope, closes admission and awaits terminal settlement inline.
  HTTP removes its closed server cache entry before invoking owned deletion.
- Owned deletion permanently retires the shared writer generation and transfers
  its actual OS lease plus retirement completion tail into the blocking worker.
  No unlock/reacquire gap is introduced. Retained stores reject future primary
  journal writes as Retired, including while removal is paused. Canceling the
  async waiter does not drop the worker's lease. Lease close precedes completion.
  The existing Weak registry and retirement latch remain intact.

## Deliberate limits

This only coordinates deletion through an explicit AppServerHandle; path-only
deletion still requires stopping work and dropping all owners. It does not
shutdown all other local runtimes or claim comprehensive API retirement.
Canonical config/image transaction ownership remains unfinished; the primary
journal/store guards are not a substitute for that work.

Validation failures preserve an already committed owner. Once a generation is
retired, a later filesystem removal failure leaves it retired (fail closed), not
resurrected across a lease gap. Cancellation before ownership transfer may leave
a closed server and existing storage; it does not force detached deletion.

A **quiescent upgrade is required**: old binaries use an internal lock and do not
coordinate with this external lease. This patch does not establish mixed-version
safety, stale-client fencing, same-UUID reincarnation protection, content-revision
fencing, malicious namespace mutation safety, or power-loss durability. It adds
no schema migration, quarantine or client-token API.

## Exact qualification plan

The source bundle contains 13 complete replacement/new files and original
Git blob IDs. The controller verifies the pinned upstream source before applying
anything. It never writes to the upstream repository.

One integration binary contains 11 mandatory cases and one intentionally ignored
child-process helper. Five expected baseline reds are individually distinguished
by assertion markers:

| Test | Required baseline assertion |
| --- | --- |
| `foreign_live_writer_blocks_deletion` | `OWNERSHIP_FOREIGN_DELETE` |
| `local_live_writer_blocks_deletion_without_deadlock` | `OWNERSHIP_LOCAL_DELETE` |
| `cold_existing_handle_cannot_recreate_deleted_session` | `OWNERSHIP_COLD_MISSING` |
| `new_for_existing_slot_cannot_recreate_deleted_session` | `OWNERSHIP_NEW_EXISTING` |
| `failed_new_materialization_consumes_creation_permission` | `OWNERSHIP_NEW_CONSUMED` |

Six positive controls cover normal owner-drop deletion, read-only opening, cold
identity/recovery rejection releasing a tentative lease, legitimate ownership
retention, and lazy construction. Five additional new unit cases cover:
panic-time tentative release versus existing-owner retention (two), canceled
owned deletion retaining a real OS lease while stale clones stay retired, invalid
owned-delete scope preserving its legitimate owner, and direct handle deletion
closing admission while a retained store cannot recreate the directory.

The direct-handle test is additionally inserted into an otherwise unchanged
baseline library using a test-only module declaration; its expected behavioral
failure marker is `OWNERSHIP_DIRECT_DELETE`. The two unchanged HTTP regressions
are mandatory baseline positive controls. Candidate library execution requires
all five new unit cases plus those two HTTP controls and the two existing writer
lifecycle controls individually. These nine names must also pass in the full gate.

Fifteen controller self-controls cover ten false-red rejections, four bounded
process/cleanup cases and exact libtest inventory parsing.

The controller compiles the baseline plus test-only additions first. It verifies
the emitted executable and exact inventory, then runs each case separately.
Compiler failures, timeout, signal, oversized output, zero/ignored/wrong tests,
or a different panic cannot count as a baseline behavioral failure. The candidate
must pass every mandatory integration and library case. Before/after source
snapshots include every authored untracked file, not only Git-tracked originals.

Finally it builds canonical fixture Modules
`7fceaebc3bed8add9b0e3091110f59deca86ba46` using that repository's own dependency
graph (Core `bee0e409e746e2df9db32748d4f8ea02201bd4af`), builds the pinned DCP worker,
then invokes candidate Core's unchanged `scripts/test.py full`. Fixture sources
are never patched to candidate Core. Actual test/reference executable and DCP
output hashes, source snapshots, bounded stage logs and status go into the receipt.
Full testing repeats focused cases; execution totals are not additive unique
coverage.

The workflow uses the supported Ubuntu 22.04 hosted label without changing
sysctls, AppArmor, or any security policy. Its ordinary package-manager
bubblewrap is too old for Core's FD-backed sandbox interface, so it builds the
official [bubblewrap v0.13.1 release](https://github.com/containers/bubblewrap/releases/tag/v0.13.1)
from the 129,472-byte archive with SHA256
`0e85c8702248b8dd64144f594147553650cdd0e4c951690345faace79c217c4d`.
The archive is size/digest-verified before extraction; Meson forbids automatic
dependency downloads and keeps SELinux support enabled. Only the resulting
verified binary is installed at Core's hardcoded `/usr/bin/bwrap` path, as
ordinary root-owned mode 0755 with no setuid/setgid or file capabilities.
The dependency's own optional tests are not run; this is not a vendor
certification. All actual Core sandbox tests remain mandatory.

A real unprivileged namespace/FD-bind probe uses the runner's default security
policy and must succeed before qualification. Unsupported flags or namespace
policy fail the lane, never trigger a weakened sandbox or skipped tests.
The hosted image is a moving supported label; the receipt captures its actual
image/version and sandbox binary hash. Availability is not presumed from source
review. [Official image inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2204-Readme.md)
and [supported runner labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
are source references, not proof that this job has executed.

The separate experimental workflow has read-only repository permissions and a
branch guard. It does not change upstream manual CI, merge, release, publish a
portable artifact, or claim speed improvements. All subprocesses have deadlines
and output budgets; cleanup covers cooperating POSIX process groups, not arbitrary
escaped descendants.
