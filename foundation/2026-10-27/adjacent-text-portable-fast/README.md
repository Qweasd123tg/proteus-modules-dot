# PR28 portable-fast qualification (draft)

This additive experiment qualifies the supported portable refresh of the exact
Desktop tree already tested by PR28. It does not change that PR, upstream source
repositories, main, queue/drop policies, protocol, or canonical journals.

## Exact input and source graph

- Reviewed bundle: modules-dot commit 88872cb2e3befbff4cfeaff4919b1dc9675195b1.
- Desktop base: 2bf38f67055f10f5ed0fd225399ba77d84756ba1.
- Apply the bundle's three PR23 prerequisites, test seam, and coalescing patch
  without modification. Complete candidate tree:
  b30533cb589c30b8ca843f0b8d05164e3a02b5b4.
- Delivery Core: 63454d4e8b1e4e6b26d088fce2a17d46f30390ae.
- Delivery Modules: 0d9c5fd18f04e6e3a083351678065c5f72966792.
- Delivery Extensions: 3361fc1650c4ac6f167c3e48a0fba8980a5c9038.
- Desktop's locked Core contracts f2ef701ef53c7bd45ba3acf58360fa1e77ddfb60 and
  Modules' locked Core dependencies f3d01053dff6113c31afbd885ef1ab1a8d931d53
  remain unchanged. They are distinct from the built delivery Core.
- The controller explicitly selects isolated source directories. This is that
  pinned integration graph, not evidence for Core's separate canonical full
  test fixture graph and not automatic sibling/default-source selection.

The source candidate is committed locally in the disposable runner before the
portable build. Its deterministic Git commit object, parent, full tree and hash
are retained. It is not an upstream commit or merge. The original patch sources
remain durable at the reviewed PR28 commit; this qualification's authored
controller and workflow are retained in their separate draft.

## Commands and bounds

The supported build command is exactly:

    python3 scripts/portable.py --fast

This builds delivery Core and reference-module release binaries, the optimized
Desktop fast profile, DCP and its locked npm dependencies, standalone hook assets,
extension binaries, tracked profiles, launchers and notices. No tar archive is
created. Every Cargo invocation in the pinned build scripts uses --locked.

Ubuntu 24.04, Rust 1.95.0, Node 22.23.4 and Python 3.12.15 are selected explicitly.
The runner image, OS/architecture/libc, tool versions and selected apt package
versions are recorded. Runner system dependencies are not immutable; this is not
a bit-reproducible build claim.
Cargo jobs are 2. Fresh source directories, targets and Cargo home are required.
The environment is allowlisted rather than inheriting target, profile, wrapper,
Git, npm or Proteus overrides. Reviewed source Cargo configuration is preserved;
unexpected ancestor configuration is rejected. No target cleanup, binary cache
reuse, or deletion of unrelated data is performed.

The job limit is 180 minutes; the controller has a 165-minute total deadline,
and the portable command has a 150-minute watchdog. Each inventory has a
120-second deadline checked while traversing and streaming file hashes.
Each command has an output-byte bound, a 64 KiB retained log tail and process
group cleanup even if its leader exits. Six synthetic controller tests cover
normal completion, time/output bounds, both inherited-pipe and closed-pipe
orphaned children, and SIGTERM. A forced host SIGKILL or job hard deadline may
prevent final evidence upload. Deliberately detached new sessions are not
qualified by the process-group tests.

At least 20 GiB must be free before building. Commands stop before crossing a
2 GiB reserve; nothing is removed to gain space. Evidence is bounded: each JSON
file at most 8 MiB, self-test report at most 2 MiB, portable inventory at most
50,000 entries including directories, and 8 GiB of regular file content.

## Required positive evidence

- Exact original bundle and all patch digests, all four source-stage trees,
  unmodified dependency lock files, source controls and Cargo configuration.
- Clean committed source identities before and after the portable build/probes.
- Embedded release-sources.json names the local candidate and the three exact
  delivery pins, all clean. It must not misidentify upstream-plus-dirty as the
  candidate.
- Native, Core and reference binaries exactly match their built target files;
  packaged extension binaries, metadata, tracked profiles and launcher bytes
  match their selected source/build inputs.
- Complete bounded file/link/directory inventory and hashes, notices, and no tar archive.
- Isolated synthetic-HOME folder probes: CLI and launcher --version; the
  supported test_portable_dcp.py and test_portable_hooks.py; extension tests/wire.py
  against the actual packaged directory. Expected positive records are required.
- The portable file/link/directory inventory is unchanged by those probes.

The workflow uploads JSON evidence and the tiny source-commit object only.
It does not upload binaries, produce a release archive, publish a release,
push source candidate commits upstream, or change PR28.

## Existing semantics and remaining limits

PR28 run 40432288991 independently passed the baseline semantic controls plus
the isolated logical work-budget red, all 16 new candidate tests, formatting,
and the canonical Desktop command with 232 unique passing tests. Its artifact
identity is recorded as prior evidence, not represented as a new run here.

The prior exhaustive named test executed 387,072 short offset/UTF-8/partition
comparisons against the production reducer. Its logical counters do not measure
allocations, elapsed speed, RSS, native frame/pixel behavior, or scroll anchors.
Unbounded queue/drain growth, auxiliary run storage, cross-batch prefix work and
Core offset/snapshot parity remain outside this qualification.

The existing upstream release workflow provides synthetic headless checks only:
its Desktop --version invocation explicitly exits before opening a window.
This qualification likewise does not exercise a native window, real streaming
scroll anchors, selection/focus, live-provider quality, or user UX. No Xvfb
process launch is substituted for those checks. Passing portable-fast is a
packaging/build milestone, not native UX qualification or merge readiness.

Implementation-time validation is source review and in-memory Python syntax
validation only until this separate hosted workflow actually succeeds.
