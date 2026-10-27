# Default-Core copy reductions and ownership-release qualification

Status: SOURCE-REVIEWED CANDIDATE; compilation, runtime controls, canonical gates and performance are NOT_RUN for this package.

## Four deliberately narrow changes

1. Persisted result callbacks avoid cloning complete history. Store-less callbacks retain their lazy snapshot and original equality/revision semantics, including non-reflexive NaN values. Recorder errors, attribution, ordering and lost-capture behavior stay unchanged.
2. An empty terminal suffix returns after accepted-prefix validation and part-ID reconciliation; full response-envelope validation still runs before success recording. A nonempty suffix follows the unchanged path.
3. A final hook event moves into the complete trace, stays there throughout the awaited immutable recorder call, and moves out only after recorder success. Handler order, trace facts and error/cancellation behavior are preserved.
4. The component-v3 parser consumes its owned envelope map and strings instead of cloning payloads. Exact fields, error chains and validation precedence are unchanged. Deserializing error.data can still rebuild containers; this is not a whole-error zero-allocation claim.

Descriptor, schema, queue/admission behavior, public APIs, dependency graphs, DCP development and shipping Modules are out of scope.

## Separate ownership-release correctness prerequisite

The first exact-head run, 40476346049 at d868f12c7b22ecb3ba67ec8f142137bc7ca07c39, remains FAILED. Its baseline controls passed, but the unchanged canonical closed_owner_can_be_deleted test saw a still-held lease after dropping its owner. Protocol and module_swap passed; source postflight and the focused phase did not run. This is retained failure evidence, not retroactively reclassified as a pass or dismissed as harmless.

A separate fifth patch makes SessionWriteOwnership explicitly unlock when dropped by its acquiring process. Close alone can leave a flock held by a duplicated or transiently inherited descriptor. An acquisition-PID guard prevents a fork child's destructor from unlocking the live parent's shared open-file-description lease. Constructing the RAII guard immediately after try_lock also covers fallible diagnostic-metadata writes. Cancellation-owned deletion still retains its actual guard until worker completion. If OS unlock fails, destructor close remains a best-effort fallback; no unconditional release guarantee under OS failure is claimed.

Two Linux-only controls use actual OS locks: a duplicated descriptor must not keep a dropped owner alive (genuine baseline red), and a real fork-child drop must not unlock the parent's live guard (baseline/candidate green). The duplicate control also proves closing the old descriptor cannot release a replacement owner's lock. Only the explicit WouldBlock branch emits the intended negative-control marker; other OS errors have a distinct diagnostic and reject qualification. Raw control teardown explicitly unlocks before closing, avoiding the same fork-retained-FD race inside the test itself. There are no sleeps, lock bypasses, hidden retries or global serialization.

The original failure log suggests, but does not by itself prove, the inherited-descriptor mechanism. The new baseline-red/candidate-green controls are mandatory before claiming the fix is qualified. Primary mechanism references are [Rust 1.95 File locking](https://github.com/rust-lang/rust/blob/1.95.0/library/std/src/fs.rs) and [Linux flock semantics](https://man7.org/linux/man-pages/man2/flock.2.html).

This correctness prerequisite is explicitly separate from the four copy reductions. The combined baseline intentionally includes its additional red; this is not a performance experiment. Any later allocation/latency/RSS comparison must apply the same qualified ownership prerequisite to both benchmark arms.

## Immutable baseline and artifact layout

The baseline is the already-qualified Core composition tree 7dec0c811a514adf32a70907635939547e0a57cf. Its source recipe and controller are pinned to personal-repository PR 35 head 72aeaa37b1f81baf105a0ec09f337237dc0b2a7f. The upstream starting commit is 63454d4e8b1e4e6b26d088fce2a17d46f30390ae. Prior run 40459018866 is provenance only; no old log can satisfy a gate in this new run.

Each of the four copy slices and the separately identified ownership prerequisite has a production patch and a test patch. The manifest binds every patch byte count, SHA-256, Git blob, source preimage and complete individual production/baseline-test/candidate-test tree. All plans are reconstructed with unique exact old hunk text before any source replacement. No fuzzy or positional fallback is used.

Combined trees:
- Pure production: 00ae23c47a5c59d11d1a9494485169e17b637f66.
- Baseline plus new test support: 5e022a2c1deb94cffa911a259173f010ffa2f6a1.
- Candidate plus new test support: ffc107268b4ed2f8685f02d318f92f25e1ab9a21.
- Focused candidate plus unchanged PR 35 recovery/deletion test control: 8c2ba00fa800d2c987c7dffbb2d0486eb8f1baa9.

These are reproducible source-tree identities, not fetchable upstream commits. The focused tree is explicitly instrumented and is never labeled pure production.

## Required fresh hosted evidence

Three isolated standard-runner jobs:
- Baseline: both affected library binaries compile and expose every exact nonignored test identity. Fourteen equivalence controls pass. Four genuine mechanism controls fail at their intended assertions: persisted callback allocation threshold, final-hook recorded output pointer, owned-frame first ID pointer, and explicit ownership release with a duplicated descriptor. Wrong executable, empty filter, compiler error, unrelated panic, signal or timeout cannot count as a red.
- Pure production: unchanged complete protocol gate, all sixteen canonical module_swap cases, and unchanged scripts/test.py full. Inherited exact custom-harness accounting retains the 26 session cases, seven sandbox checks, mandatory component names, five explicitly allowed ignores and the two known nested helper executions. No authored allocator instrumentation enters this tree.
- Focused candidate, after both preceding jobs pass: all eighteen exact new/expanded controls pass; the unchanged recovery/owned-deletion control passes all four distinct schedules; the complete Core library suite runs with normal four-thread scheduling; the complete protocol suite runs with all new parser cases required. Only the existing manual benchmark ignores are allowed.

The history resource control is one test, not two baseline reds: baseline stops at its first bound-case assertion; candidate additionally covers the unbound arm. Zero/known-allocation/legacy-clone controls establish threshold sensitivity, not an exact allocator overhead delta. The suffix controls are semantic equivalence checks, not an artificial optimization red.

There are seventeen newly authored tests and one expanded existing test among the eighteen focused cases. Repeated direct, package and full-suite executions are not additional unique tests. Prior overlap coverage is reported separately.

Each phase verifies source/index integrity after execution, current binary identities, compile source/default-feature bindings and fresh source trees. An always-attempted aggregator requires all three exact head/run/attempt receipts, successful GitHub phase jobs, bounded raw-log hashes, real sandbox prerequisite evidence and independent reclassification of every required outcome. A generic PASS field is insufficient. Old-attempt artifacts cannot fill missing current-attempt phases.

## Reused support and resource policy

The unchanged reviewed controller imports only the SHA-256-verified PR 35 support module. Its top-level source contains standard imports, constants, classes, functions and a guarded main; the old qualification/aggregation entry points are never called. Reviewed source-recipe, bounded-runner and canonical-parser helpers are reused rather than copied into a second framework. New orchestration and assertion classifiers still require independent review.

Only standard ubuntu-22.04 ephemeral runners are selected, at most two phases concurrently. Initial admission is eight GiB free; Runner-managed commands stop below two GiB. Each controller has a 110-minute deadline and each phase job a 150-minute bound; aggregate is ten minutes. Runner-managed source/build output and logs are bounded. Official setup steps have step/job timeouts and the initial admission check, not the same continuous disk/output sampling; the controller rechecks admission after setup. Resource exhaustion, deadlines and process/output limits are infrastructure failures, never successful negative controls. No manual deletion, target cleanup, paid runner or larger runner is used.

Actions are pinned to reviewed commit SHAs. Hosted setup uses official Rust 1.95.0, Node 22.18.0 and size/digest-verified bubblewrap 0.13.1 as ordinary root-owned mode 0755. No setuid, capabilities, sysctl, AppArmor or security-policy changes. A real unprivileged namespace/FD probe and canonical sandbox tests are required.

The canonical fixture remains Proteus-modules 7fceaebc3bed8add9b0e3091110f59deca86ba46 with its unchanged bee0e409e746e2df9db32748d4f8ea02201bd4af SDK graph. Its DCP worker is built only as the unchanged existing canonical regression dependency where required by the production and focused gates. No stopped DCP candidate, optimization, source/metadata edit or advisory submission is used. Explicit npm installs disable scripts, audit and funding; all descendants inherit both lowercase and uppercase audit suppression. Child environments are allowlisted; application tokens/secrets and arbitrary build overrides are not inherited.

The personal repository receives only this additive experimental package and guarded workflow; all prior base files remain byte/mode-identical. No upstream writes, merge, release, deployment or production-session access occurs.

## Evidence limits

Preparation used connector reads, in-memory source/hash reconstruction and strict hunk replay; official installed rustfmt stdin/stdout; and source-only Python AST/YAML parsing. No local product source, tests, builds or controller orchestration ran. The protected low-disk preparation machine was not cleaned or modified.

Source-proven clone elimination and unexecuted controls are not measured throughput, latency, RSS or full-agent gains. Actual AgentRuntime benchmarking is a separate follow-up, not a substitute for this correctness qualification.
