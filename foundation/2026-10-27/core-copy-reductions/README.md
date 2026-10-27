# Default-Core copy-reduction qualification

Status: SOURCE-REVIEWED CANDIDATE; compilation, runtime controls, canonical gates and performance are NOT_RUN for this package.

## Four deliberately narrow changes

1. Persisted result callbacks avoid cloning complete history. Store-less callbacks retain their lazy snapshot and original equality/revision semantics, including non-reflexive NaN values. Recorder errors, attribution, ordering and lost-capture behavior stay unchanged.
2. An empty terminal suffix returns after accepted-prefix validation and part-ID reconciliation; full response-envelope validation still runs before success recording. A nonempty suffix follows the unchanged path.
3. A final hook event moves into the complete trace, stays there throughout the awaited immutable recorder call, and moves out only after recorder success. Handler order, trace facts and error/cancellation behavior are preserved.
4. The component-v3 parser consumes its owned envelope map and strings instead of cloning payloads. Exact fields, error chains and validation precedence are unchanged. Deserializing error.data can still rebuild containers; this is not a whole-error zero-allocation claim.

Descriptor, schema, queue/admission behavior, public APIs, dependency graphs, DCP development and shipping Modules are out of scope.

## Immutable baseline and artifact layout

The baseline is the already-qualified Core composition tree 7dec0c811a514adf32a70907635939547e0a57cf. Its source recipe and controller are pinned to personal-repository PR 35 head 72aeaa37b1f81baf105a0ec09f337237dc0b2a7f. The upstream starting commit is 63454d4e8b1e4e6b26d088fce2a17d46f30390ae. Prior run 40459018866 is provenance only; no old log can satisfy a gate in this new run.

Each slice has a separate production patch and test patch. The manifest binds every patch byte count, SHA-256, Git blob, source preimage and complete individual production/baseline-test/candidate-test tree. All plans are reconstructed with unique exact old hunk text before any source replacement. No fuzzy or positional fallback is used.

Combined trees:
- Pure production: 3ac78ba4580230e6a1e14eb70685e2879bcca976.
- Baseline plus new test support: 553184986cf87994b9031e8f51012c0842b4e5b0.
- Candidate plus new test support: dbe866b81ec6720d5354489eb9ed253c440f1164.
- Focused candidate plus unchanged PR 35 recovery/deletion test control: b1432a1e9cbc815f99d92771174de8a3f9362d24.

These are reproducible source-tree identities, not fetchable upstream commits. The focused tree is explicitly instrumented and is never labeled pure production.

## Required fresh hosted evidence

Three isolated standard-runner jobs:
- Baseline: both affected library binaries compile and expose every exact nonignored test identity. Thirteen equivalence controls pass. Three genuine mechanism controls fail at their intended assertions: persisted callback allocation threshold, final-hook recorded output pointer, and owned-frame first ID pointer. Wrong executable, empty filter, compiler error, unrelated panic, signal or timeout cannot count as a red.
- Pure production: unchanged complete protocol gate, all sixteen canonical module_swap cases, and unchanged scripts/test.py full. Inherited exact custom-harness accounting retains the 26 session cases, seven sandbox checks, mandatory component names, five explicitly allowed ignores and the two known nested helper executions. No authored allocator instrumentation enters this tree.
- Focused candidate, after both preceding jobs pass: all sixteen exact new/expanded controls pass; the unchanged recovery/owned-deletion control passes all four distinct schedules; the complete Core library suite runs with normal four-thread scheduling; the complete protocol suite runs with all new parser cases required. Only the existing manual benchmark ignores are allowed.

The history resource control is one test, not two baseline reds: baseline stops at its first bound-case assertion; candidate additionally covers the unbound arm. Zero/known-allocation/legacy-clone controls establish threshold sensitivity, not an exact allocator overhead delta. The suffix controls are semantic equivalence checks, not an artificial optimization red.

There are fifteen newly authored tests and one expanded existing test among the sixteen focused cases. Repeated direct, package and full-suite executions are not additional unique tests. Prior overlap coverage is reported separately.

Each phase verifies source/index integrity after execution, current binary identities, compile source/default-feature bindings and fresh source trees. An always-attempted aggregator requires all three exact head/run/attempt receipts, successful GitHub phase jobs, bounded raw-log hashes, real sandbox prerequisite evidence and independent reclassification of every required outcome. A generic PASS field is insufficient. Old-attempt artifacts cannot fill missing current-attempt phases.

## Reused support and resource policy

The small new controller imports only the SHA-256-verified PR 35 support module. Its top-level source contains standard imports, constants, classes, functions and a guarded main; the old qualification/aggregation entry points are never called. Reviewed source-recipe, bounded-runner and canonical-parser helpers are reused rather than copied into a second framework. New orchestration and assertion classifiers still require independent review.

Only standard ubuntu-22.04 ephemeral runners are selected, at most two phases concurrently. Initial admission is eight GiB free; Runner-managed commands stop below two GiB. Each controller has a 110-minute deadline and each phase job a 150-minute bound; aggregate is ten minutes. Runner-managed source/build output and logs are bounded. Official setup steps have step/job timeouts and the initial admission check, not the same continuous disk/output sampling; the controller rechecks admission after setup. Resource exhaustion, deadlines and process/output limits are infrastructure failures, never successful negative controls. No manual deletion, target cleanup, paid runner or larger runner is used.

Actions are pinned to reviewed commit SHAs. Hosted setup uses official Rust 1.95.0, Node 22.18.0 and size/digest-verified bubblewrap 0.13.1 as ordinary root-owned mode 0755. No setuid, capabilities, sysctl, AppArmor or security-policy changes. A real unprivileged namespace/FD probe and canonical sandbox tests are required.

The canonical fixture remains Proteus-modules 7fceaebc3bed8add9b0e3091110f59deca86ba46 with its unchanged bee0e409e746e2df9db32748d4f8ea02201bd4af SDK graph. Its DCP worker is built only as the unchanged existing canonical regression dependency in the production phase. No stopped DCP candidate, optimization, source/metadata edit or advisory submission is used. Explicit npm installs disable scripts, audit and funding; all descendants inherit both lowercase and uppercase audit suppression. Child environments are allowlisted; application tokens/secrets and arbitrary build overrides are not inherited.

The personal repository receives only this additive experimental package and guarded workflow; all prior base files remain byte/mode-identical. No upstream writes, merge, release, deployment or production-session access occurs.

## Evidence limits

Preparation used connector reads, in-memory source/hash reconstruction and strict hunk replay; official installed rustfmt stdin/stdout; and source-only Python AST/YAML parsing. No local product source, tests, builds or controller orchestration ran. The protected low-disk preparation machine was not cleaned or modified.

Source-proven clone elimination and unexecuted controls are not measured throughput, latency, RSS or full-agent gains. Actual AgentRuntime benchmarking is a separate follow-up, not a substitute for this correctness qualification.
