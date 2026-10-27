# Default-Core copy reductions and bounded correctness qualification

Status: SOURCE-REVIEWED CANDIDATE. This package's fresh compilation, runtime gates and aggregate qualification are NOT_RUN. Performance is unmeasured.

## Runtime scope

Four deliberately narrow copy reductions:
1. Persisted result callbacks avoid cloning complete history. Store-less callbacks retain their lazy snapshot and equality/revision semantics, including non-reflexive NaN values.
2. An empty terminal suffix returns after accepted-prefix validation and part-ID reconciliation. Full response-envelope validation still runs before success recording; a nonempty suffix follows the unchanged path.
3. A final hook event moves into the complete trace, remains there throughout the awaited immutable recorder call, and moves out only after recorder success.
4. The component-v3 parser consumes its owned envelope map and strings. Exact fields, error chains and validation precedence are retained. Deserializing error.data may still rebuild containers; this is not a whole-error zero-allocation claim.

Two separately identified correctness prerequisites:
- Ownership release: SessionWriteOwnership explicitly unlocks on drop only in its acquiring process. This releases a lease despite duplicate/inherited descriptors without letting a fork child unlock the parent's live lease. The RAII guard is constructed immediately after successful try_lock, before fallible diagnostic writes. Existing cancellation-owned worker lifetime is retained. Unlock failure remains best effort with close fallback; no unconditional release guarantee under OS failure is claimed.
- Configuration revalidation: the existing 300 ms metadata polling fast path remains. An actual semantic scan's start time bounds reuse of metadata-only hints; pending changes and an overdue scan bypass the hint. The provisional maximum scan age is three seconds, not a scheduler or end-to-end publication deadline. Existing two-stable-sample behavior, last-good state, failed-fingerprint suppression, path locking, pre/post refresh validation, weak ownership and cancellation selects are retained. The age advances on actual scan attempts, including failures, not idle polls; a slow attempt does not earn a fresh interval after completion.

The polling control seam adds no production channel, oneshot, Box or new heap allocation on metadata-only fast polls. Scheduled semantic scans still run the existing allocating loader/fingerprint path more often than an indefinitely skipped poll; that cost is unmeasured. The reviewed source retains cfg(test) driver/report support verbatim; Rust excludes those fields and reporting Drop from shipping compilation. In a Core libtest build, test-only report fields exist, but ordinary canonical watcher tests use Polling::new with requests=None and force_current=false. They do not activate the manual driver. No new counting allocator is present in the production lane.

Three seconds is a provisional latency/idle-cost tradeoff awaiting measurement. This does not promise observation of every transient edit, cancellation around every loader await, complete recursive skill/body watching, plugin canonical-root fingerprint repair, reload-tools scope repair, a global watcher service or assembly retry/backoff changes. Those distinct gaps are not silently included. No whole-file hashing or native filesystem-event dependency is introduced.

## Explicit source and fixture partition

The immutable source anchor is the already-qualified Core composition tree 7dec0c811a514adf32a70907635939547e0a57cf, reconstructed through personal-repository PR 35 head 72aeaa37b1f81baf105a0ec09f337237dc0b2a7f from upstream commit 63454d4e8b1e4e6b26d088fce2a17d46f30390ae. Earlier run 40459018866 is provenance only, never current-run evidence.

The original five copy/ownership slices retain separate production and test patches and their 15 independent source plans. Configuration is explicitly partitioned:
- Runtime/docs: complete reviewed profile_watch.rs, polling.rs, ConfigInputs factoring and configuration documentation.
- Shared canonical fixture: the existing low-level inputs test file is amended. Equal-length instruction writes have an explicitly distinct, read-back-verified mtime. Directory dependency detection uses an explicitly changed cloned directory stamp through the same API-private comparison routine. Existing disappearance/include/plugin/atomic-replacement/symlink checks remain.
- Focused/legacy support: new watcher test registrations plus gate and bounded-age test files.
- Legacy negative control: the single reviewed age predicate is reverted to unlimited metadata-only skipping, with otherwise identical configuration instrumentation and fixtures.

This is an amended canonical test fixture, not an unchanged canonical test source. The metadata-only ConfigInputs comparison itself is not a content detector. End-to-end bounded-age coverage instead uses the actual loader and publisher with per-instance stale-positive metadata hints and manually supplied monotonic poll instants. It does not reproduce or prove a historical filesystem timestamp collision.

The combined baseline is not the untouched 7dec binary: it includes the shared configuration refactor, identical test support/fixtures and legacy gate. The original five runtime fixes remain absent there. The production lane includes all six runtime changes and the disclosed shared fixture, but retains the original watcher test registrations and does not activate the manual driver. Focused includes all candidate test support and the retained PR 35 recovery/deletion control.

The manifest binds every patch byte count, SHA-256, Git blob, exact preimage, file role and complete source tree. All 23 plans are reconstructed using unique complete old hunk text before replacement; no fuzzy or positional fallback is used.

Combined trees:
- Production runtime plus disclosed canonical fixture: fc0ba40cccf23c5d12a349a1a34ec6470c2eddb4.
- Instrumented legacy configuration/copy baseline: a1a128f5f42c5b87c14e064e2c097cad00095ca8.
- Candidate plus test support: ac3e653f0fa02b48815542a94ac5d8394b2fe509.
- Focused plus retained overlap control: 71b3ae5effb9df6faaeb4846c3a4733b3e8ddd44.

These are reproducible source-tree identities, not fetchable upstream commits.

## Fresh hosted gates

Three isolated standard-runner source jobs remain, with no extra build arm:
1. Baseline: compile both affected default-feature library binaries and verify exact nonignored identities. Preserve all original 18 copy/ownership controls: 14 semantic greens and four genuine reds. Add only the one explicit legacy configuration content-assertion red. Total: 19 direct controls, 14 greens and five intended reds.
2. Production: complete protocol, all 16 canonical module_swap identities, and scripts/test.py full, using the disclosed fixture amendment. All 76 required full-suite identities, 26 exact custom session cases, seven real sandbox checks, five existing allowed ignores and two source-pinned nested helper executions are bound and reclassified.
3. Focused, only after both preceding jobs succeed: all 26 direct controls pass, including all eight configuration controls. The seven nonnegative configuration controls are candidate-only, not baseline-equivalence claims. Retained recovery/owned-deletion coverage must show all four distinct schedules. The complete Core library runs with normal four-thread scheduling and all 45 mandatory identities; the complete protocol suite includes all new frame cases. Only existing manual benchmark ignores are allowed.

The manifest explicitly lists the ordered baseline and focused case identities. Execution and aggregation resolve the same lists and reject unknown, duplicated, empty or incomplete inventories. Hosted self-controls also validate the actual package inventories before source builds.

The configuration negative control requires all bounded poll acknowledgments and the specific final assertion showing old first versus expected other. A timeout, compile failure, setup failure, different assertion or wrong result is not an accepted red. Gate controls cover deadline equality, pending bypass, metadata fast path and no deadline sliding. Other controls cover persistent directory additions, read-error recovery, last-good retention, failed-fingerprint suppression, cancellation/owner release, closed-driver release and unchanged revalidation without rebuild. The closed-driver test observes owner release, not a direct task-join completion claim.

The history resource control counts as one baseline red: the first bound arm fails, while its unbound arm is candidate coverage. Zero/known-allocation/legacy-clone checks prove threshold sensitivity, not an exact overhead delta. Empty-suffix tests are semantic equivalence controls, not an artificial optimization red.

Among the 26 direct focused cases, 25 names are newly authored and one existing suffix test is expanded. The separately amended metadata fixture retains its existing name. Repeated direct/package/full executions and prior overlap coverage are never added as extra unique tests.

Every phase verifies source/index postflight, compile target/source/default features, binary identities and fresh source trees. The always-attempted aggregator requires exact head/run/attempt receipts, successful phase jobs, sandbox evidence, bounded raw-log hashes and independent reclassification. Complete parser/receipt objects are compared as canonical JSON strings: tuple/array serialization is normalized without discarding fields, ordering or scalar types. Boolean values cannot replace integer counts. A generic PASS field or old-attempt artifact is insufficient.

## Retained failed runs

All three predecessors remain FAILED:
- 40476346049 at d868f12c7b22ecb3ba67ec8f142137bc7ca07c39: closed_owner_can_be_deleted observed a still-held lease. The historical holder is not identified by the log; duplicate/fork controls qualify the repair mechanism separately.
- 40480504769 at 2e93dc9d3b0da720829479ccec22cd63aca21ff7: all source jobs passed, but aggregate Python tuple/list comparison rejected matching serialized protocol evidence. The narrowly reviewed canonical-JSON correction and rejection controls address that controller defect.
- 40483121449 at 7633a90dc9694d75767c1b77d68815f9c10132dc: the low-level config test's immediate equal-length rewrite failed its invalidation assertion. Metadata stamps were not recorded, so the exact collision is not proven. Caller/documentation review exposed indefinite metadata-only skipping, motivating the bounded-age runtime prerequisite rather than merely narrowing the test.

No old source-phase pass qualifies this new head, and no failed run is retrospectively relabeled successful.

## Resource and safety policy

Only standard ubuntu-22.04 ephemeral runners are selected, at most two source jobs concurrently. Initial admission is eight GiB free; Runner-managed commands stop below two GiB. Each controller has a 110-minute deadline and each source job a 150-minute bound; aggregate is ten minutes. Source/build output and logs are bounded. Official setup steps have step/job timeouts and admission checks, not identical continuous Runner sampling. Resource exhaustion, process/output limits and deadlines are infrastructure failures, never successful reds. No cleanup, target deletion, paid runner or larger runner is used.

Actions are pinned to reviewed commit SHAs. Setup uses official Rust 1.95.0, Node 22.18.0 and size/digest-verified bubblewrap 0.13.1, root-owned mode 0755 without setuid/capabilities/security-policy changes. A real unprivileged namespace/FD probe and canonical sandbox tests are required.

The canonical fixture remains Proteus-modules 7fceaebc3bed8add9b0e3091110f59deca86ba46 with unchanged bee0e409e746e2df9db32748d4f8ea02201bd4af SDK graph. Its DCP worker is only the existing unchanged canonical regression dependency where production/focused gates require it. There is no new DCP development, optimization, metadata edit or advisory submission. Explicit npm installs disable scripts, audit and funding; descendants inherit lowercase and uppercase audit suppression. Child environments are allowlisted; application secrets/tokens and arbitrary build overrides are not inherited.

The controller reuses only SHA-256-verified PR 35 source-recipe, bounded-runner and parser support. Old qualification/aggregation entry points are never called. Personal-repository changes are an additive experimental package and guarded workflow; all original main files remain byte/mode-identical. No upstream write, merge, release, deployment or production-session access occurs.

## Evidence limits

Preparation uses connector reads, in-memory source/hash reconstruction and exact hunk replay, installed official rustfmt stdin/stdout, source-only AST/YAML/symbol-table inspection and narrowly approved pure data helpers. No local product code, build, test or full controller orchestration is executed. Static checks and pure helper controls are not runtime qualification.

Copy removal is not a measured full-agent throughput, latency or RSS gain. Configuration idle cost and the provisional three-second policy remain unmeasured. Any later performance A/B must apply both qualified ownership and configuration prerequisites identically to both arms; benchmarking is separate from this correctness gate.
