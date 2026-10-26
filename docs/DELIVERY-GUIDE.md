# Proteus modules: what to try, what was checked, what stays in Core

**Snapshot: 2026-10-26, 09:26 UTC. Draft deliveries, not a release.**
The repository's [main snapshot][main] contains only its initial README. The
deliveries below are open, unmerged **draft PRs** on different branches. Follow
the immutable links: the default repository view does not contain these packages.
No combined checkout, installer, production deployment or composite-tested release
is supplied. This guide changes documentation only.

## Start with the boundary you need

- **Planning or context selection:** PR1's Pi/Letta examples; they recommend/select
  data without acquiring authority. For local instruction discovery, use PR5 and
  read the separate actual-Core observations in PR10.
- **Evidence before completion:** PR4's strict JSON producer/consumer pair, not a
  free-text “tests passed” claim. PR16 adds a pinned actual-turn/official-reader
  stand. PR11 instead verifies exact quote bytes; it does
  not establish truth, provenance or a passed test suite.
- **Existing JavaScript hooks:** PR2 is a deliberately narrow command-hook adapter;
  PR8 is an opt-in numeric replacement guard, not a replacement for host admission.
- **Compatibility or performance decisions:** use the scoped probes below. An
  observed parser difference, SDK behavior or debug timing is not a migration,
  universal speedup or production guarantee.
- **Architecture and recovery:** begin with [operator/reliability research][operator]
  and [ecosystem research][ecosystems]. Source studies are not executed defects or
  comprehensive audits.

## 1. Modules, helpers and app consumers

Each row's evidence is independent. Package tests, process-wire fixtures, actual
Core checks and synthetic validator controls are **not interchangeable or additive**.

| Package / draft | What it does | Accepted evidence and important limit |
|---|---|---|
| [Pi ready steps][pi] · [#1][pr1] | `tool/v6`: validates a bounded DAG and recommends ready nodes. | Unit plus direct executable-wire checks in [CI][ci1]. Statuses are caller-supplied, unverified data; no execution, authorization, durable workflow or rollback. |
| [Letta evidence blocks][letta] · [#1][pr1] | `context_provider/v4`: selects complete versioned/tombstoned blocks within a byte budget. | Unit and own-executable wire checks in [CI][ci1]. Not a Letta service, persistent memory, provenance proof or ACL. |
| [Hermes evidence gate v1][hermes] · [#1][pr1] | `hook/v6`: requires a later receipt from the configured verifier after mutation. | Policy and own-executable wire checks in [CI][ci1]. A separate trusted receipt-emitting verifier is required; v1 does not pin exact expected suite/config/assertion coverage. |
| [Claude command hooks][claude] · [#2][pr2] | Standalone Node/POSIX adapter for a `strict_subset` of `PreToolUse`/`Stop`. | 33 authored adapter/SDK cases; [exact-head CI][ci2]. Not full Claude compatibility or a sandbox. Execution needs explicit operator `allow_execution=true`; discovered foreign hooks were not run. |
| [Strict JSON pair][strict] · [#4][pr4] | JSON assertion tool + matching Hermes v2 gate + bounded receipt contract. | 81 workspace and 8 independent Rust tests; **separate** 18 Python artifact controls; [CI][ci4]. Producer/gate policy and wire behavior are tested, but this package's reader/history fixtures are synthetic. Hashes bind observed bytes/configuration, not honesty. |
| [Portable skill catalog][skills] · [#5][pr5] | Context provider + tools: explicit local roots, namespaced IDs, digest/path-bound load and refresh. | 29 behavior cases and one own-executable wire case; [CI][ci5]. Metadata such as `allowed-tools` stays data; no scripts/hooks run. Native skill-pack already provides catalog/body-on-demand: the delta is explicit roots, identity and bounded loading. See PR10 for the separate Core layer. |
| [JS argument replacement guard][guard] · [#8][pr8] | Zero-dependency helper rejects unsafe integer-valued Numbers in an opted-in handler's outbound replacement. | [Accepted local retest supplement][guard-result]: 38 JS controls and 13 SDK hook calls + initialize; **separate** 45 Python controls. **No new remote CI acceptance.** Cannot recover earlier rounding, freeze the object or constrain a later unguarded handler. An ordinary hook error does not prove tool nonexecution or rollback. |
| [Evidence spans][spans] · [#11][pr11] | `evidence.verify_spans`: checks exact UTF-8 byte spans against one host-read buffer; includes pure checked-read support. | 32 policy + 5 helper + 2 own-executable wire Rust cases; **separate** 23 Python validator and 35 mocked envelope controls; [push][ci11]/[PR repeat][ci11pr]. Reader is synthetic here; no actual-Core call or source authenticity/semantic entailment/freshness proof. |
| [Usage attribution][usage] · [#15][pr15] | App-side stdin consumer of a supplied `SessionUsageSnapshot`; **not a process module**. Groups recorded usage while preserving unknown counters. | 31 projection + 6 own-stdin Rust tests; **separate** 35 mocked envelope, 34 synthetic validator and 6 live supervisor controls; [accepted push CI][ci15]. PR repeat CI is green; independent repeat-artifact signoff remains pending. No Core transport, provider calls, hidden-retry inference or audited billing. The authored fixture's 1,380 known-subset tokens are not total spend. |

**Receipt choice is exclusive.** Hermes v1 and strict-v2 binaries have different
names but reuse `hook/hermes.verify_evidence`. Do not register both generations:
duplicate exports are rejected even if a tool is not enabled. The historical v1
JSON producer is not delivered in PR1; it and the strict producer likewise reuse
`tool/verification.json_contracts` and must not be loaded together. Strict mode uses the compiled
`strict_json_policy` helper and explicit `on_exhaustion = "error"`. The reader must
still be registered, enabled and permitted separately; a matched weak assertion
suite is still weak verification.

**Historical document warning:** some frozen package READMEs still say “pending”
or “unrun”. They describe preparation time, not a new failure. Read the linked
exact-head PR/run and any explicit supplement for subsequent acceptance; never
silently transfer that acceptance to another source revision or integration layer.

## 2. Test stands and decision probes — not installable features

| Stand / draft | Actually exercised | What the result does not establish |
|---|---|---|
| [Core smoke][core-smoke] · [#3][pr3] | 21 model-free checks through pinned **Core3f** AppConfig/catalog/assembly, BoundTools, policy, hook and context-provider boundaries; [CI][ci3]. | No complete agent turn, official reference-pack boot, model request, journal/replay or descendant-settlement proof. Synthetic receipt history is not a real verifier. |
| [rmcp lifecycle][rmcp] · [#6][pr6] | Actual `rmcp = 3.3.0`: 12 typed-decode, 2 authored responder and 19 SDK lifecycle cases; **separate** 8 Python controls; [CI][ci6]. | Not a Proteus module, Core custom transport test or full MCP conformance. Initialize/Discover/Auto and protocol-era distinctions do not grant remote metadata authority; kill/reap does not undo remote effects. |
| [Native read cache][cache] · [#7][pr7] | Actual **Core1fc** temporary-data correctness checks, bounded owned-open traces and separately classified measurements; [CI][ci7]. | Debug/shared-runner observations and allocator-requested bytes are not RSS, copied bytes, production latency or a universal speedup. No installer is supplied. |
| [Core + portable skills][core-skills] · [#10][pr10] | 11 actual **Core3f** registry/context-callback/BoundTools checks: successful load, stale digest refresh, path mismatch, disabling, default-deny and output bounds; [push][ci10]/[PR repeat][ci10pr]. Separate verifier/capture/envelope controls remain separate. | Not a full turn, TOML/reference-pack boot, latest-Core compatibility or cancellation settlement. Provider disabling alone does not revoke the independently configured tool. Sampled resource guards are not hard quotas; all-descendant termination remains unproven. |
| [Typed Frontmatter comparison][parser] · [#12][pr12] | 174 recorded Rust **observations**, not 174 ordinary passing assertions: 152 typed/module, 7 envelope, 15 budget; **separate** 35 helper controls; [CI][ci12]. Compares exact frozen typed fields using `serde_yaml 0.9.34+deprecated`, `yaml_serde 0.10.7`, `serde-saphyr 2.0.0`. | **No parser replacement; `migration_acceptance = not_granted`.** Saphyr has four acceptance differences. Both parsers rejecting input does not imply equivalent diagnostics. No whole-module/Core, security audit or performance pass. |
| [Atomic append-group probe][append] · [#13][pr13] | Actual **Core1fc** `SessionStore::append_history`: 29 owned Core children, including duplicate rollback controls and fresh-process reopens; **separate** 40 helper controls; [CI][ci13]. Final DTO/UUID/value equality and exact rejection behavior checked. | Equal final history does not equal equal transaction/durability/crash visibility. Production callers already batch. Do not delay user-message, tool-intent or effect barriers. No power-loss, model/provider, physical-effect or universal speedup proof. |
| [Strict full-turn + official reader][strict-host] · [#16][pr16] | **7 fresh actual AgentRuntime turns**, plus **1 separate direct BoundTools default-deny case**, with official write/read, exact Ask/approval, strict receipts, canonical history and native journal reconciliation; [accepted push CI][ci16]. Separate prerequisites: 5 live Linux cleanup controls and 16 Rust fixture tests; helper/mock layers remain separate. | Validates only the pinned offline authored assembly: Core3f host/strict pair, official Modules7f executable with SDKbee0 in separate graphs. No live model, arbitrary-profile compatibility, network sandbox or universal descendant guarantee. The observed owned-child sets were empty; PR repeat acceptance is pending. |

### Incoming gates — not accepted runtime deliveries yet

- **Correction-memory CAS:** Linux SQLite correction proposal/revision/replay
  example, with nested spans-verifier dependency. Lock resolution alone is not a
  compile/test pass: [lock-only run][ci-cas-lock] at
  `d84cb4ee6d482dadf0f4ba53e8e586fed4309d21` accepted dependency resolution, not
  69 authored tests. The separate runtime gate is pending. Postcommit response loss
  can hide a real effect: same operation ID + same payload is the recovery design,
  not permission to invent a new ID or assume cancellation rolled back a commit.
- **Current-Core portable-skills compatibility:** planned separate host Core+SDK1fc
  variant with the unchanged portable executable on SDK3f and separate build graphs.
  Its same eleven scenarios are not accepted yet; PR10 remains the original Core3f
  result, not proof of this newer host pairing.

## 3. Research and operator documentation

| Draft / entry | What is delivered | Evidence boundary |
|---|---|---|
| [Baseline research][baseline-research] · [#1][pr1] | Broad initial catalog and priorities alongside the three examples. | Catalog entries include mechanisms, limits, hypotheses and rejected hypotheses—not a bug total or full audit. |
| [Operator/reliability][operator] · [#9][pr9] | Recovery runbook, extension-boundary matrix, static research-team recipe and [reliability index][reliability]. | Source studies and explicitly labeled authored reference observations. No new runtime pass for this public composition, installer or automatic retry policy. Read the matrix's mandatory [guard qualification][guard-qualification]. |
| [Ecosystem catalog][ecosystems] · [#14][pr14] | Pinned Round1–4 reports and Round1–8 synthesis, exact coverage/pins and mandatory qualifications. | Report-only publication; no runtime CI was triggered. Historical synthesis is dated 02:18 UTC. Baseline 90 entries, later 66 entries and 16 synthesis groups overlap and **must not be summed**. LiveKit “completed” is not acoustic-delivery proof; cancellation grace is not hard preemption. |

## 4. Branches and pins: do not combine by accident

PR1 and PR2 independently target `main`. PR3–9 and PR11–15 target PR1's branch;
they are **siblings**, not a sequence. PR10 targets PR5's branch and therefore
includes PR5, not all siblings. PR16 builds on PR4; the CAS
candidate builds on PR11. A Git stack states source ancestry, **not** tested
coactivation or authority inheritance. This guide's branch is based only on PR1.

Runtime assembly is separate: Hermes needs its matching verifier; the portable
provider and tools need intentionally aligned roots/disabled settings; spans needs
a registered, enabled and permitted full-read `read_file` implementation. The CAS
candidate additionally needs spans and that reader. Nothing in branch ancestry
automatically configures or authorizes these dependencies.

| Named input | Exact identity / scope |
|---|---|
| Authored Rust SDK and older Core integration baseline (“Core3f”) | `3f36a003b4f3fde2242fc80f7aedac00dd127d1d` |
| Comparison/current-Core snapshot (“Core1fc”) | `1fc3ef223d10322815dd9290a50d045bc95402bb`; used by native-cache/append probes, not retroactively by all modules |
| Official Modules (“Modules7f”) | `7fceaebc3bed8add9b0e3091110f59deca86ba46` |
| Official Modules' own SDK (“SDKbee0”) | `bee0e409e746e2df9db32748d4f8ea02201bd4af`; not silently upgraded to Core3f |
| PR2 JS adapter | Original SDKbee0 pin with exact five-file checks; selected equality at Core3f is not whole-SDK or Core-runtime equivalence |
| PR8 optional JS probe | Exact five-file SDK hashes corresponding to Core1fc; trusted separately provisioned Node/SDK required |

Some example profiles name a different official Modules pin (`04114bbe85f179895e2b8553b6169a284caaeae3`); read
their own locked configuration rather than substituting Modules7f. A source diff
or selected-file equality does not establish runtime compatibility.

## 5. Small, explicit reproduction — no installer

Choose **one immutable checkout** and inspect its README before execution. Do not
reset an existing worktree, merge siblings, install tools or run an arbitrary
imported hook just to follow this guide. A missing runtime/dependency or inadequate
disk reserve is **not run**, never a pass. The guide itself performs no execution.

For the smallest no-network/no-SDK exercise, use PR8 exact commit
`7d3bddaa2e49584ab04c5a78800e66e19dc182f4`, a trusted installed Node runtime and Python,
and work from `examples/js-argument-replacement-guard/`. These commands are copied
unchanged from its [README][guard] and [optional probe README][guard-optional]:

```sh
node test-guard.mjs
python3 -I -B -S optional-sdk/test_oracle.py
python3 -I -B -S optional-sdk/test_controller.py -v
```

They cover, respectively, 38 pure JS controls, 18 synthetic Python oracle
controls, and 9 lifecycle mocks—not the optional actual-SDK probe, Core or real
tools. They do not install dependencies. Use the optional README's separate
hash-bound, resource-checked recipe only after provisioning its trusted inputs.

Rust/Core recipes are intentionally **not reduced to one universal command**.
Each immutable package README defines its working directory, lockfile, target
graph and artifact contract. For example, [Core skills][core-skills] explicitly
requires the matching portable package; [rmcp][rmcp] is standalone. Their gates
can fetch locked dependencies and build binaries, so use a separately provisioned,
adequately sized build environment and the enclosing resource envelope—not an
unreviewed copy/paste on a nearly full machine. A unit-only command cannot reproduce
a wire, Core, full-turn or artifact-validation claim.

## 6. Prioritized architecture recommendations

These are engineering recommendations derived from the scoped evidence above,
not newly implemented guarantees. See the [boundary matrix][matrix] and
[reliability evidence][reliability] for source-level qualifications.

1. **Keep the stable authority/effect core small.** Core owns effective arguments,
   admission, approval, call identity/lineage, cancellation state, canonical history
   and settlement. Keep tool errors, timeout/cancel reports and actual physical
   effects distinct. Use recorded disposition and operator authorization before
   retry; protocol success and model prose are not an objective verifier.
2. **Make extensions opt-in and narrow.** Prefer advisory planning, bounded context,
   explicit-root skill loading and typed evidence producers/consumers over a new
   global orchestration runtime. Registration, enabled tools, policy and approval
   are separate steps. `ReadOnly`, metadata, a process boundary and minimal env are
   not an OS sandbox. Imported instructions remain untrusted data.
3. **Pair producer and consumer on the same evidence contract.** Require exact
   call/config/source/coverage bindings; preserve unsupported/unknown outcomes.
   Choose meaningful assertions and a separately trusted reader/hook chain. CAS
   adds storage/idempotency concerns that byte matching alone cannot solve. Preserve
   ambiguous postcommit outcomes rather than translating every error to “no effect”.
4. **Change compatibility or performance only behind matched gates.** Parser
   migration needs an explicit semantic decision plus existing behavior/wire/Core
   retests. MCP changes need actual host-transport/consumer proof, not only SDK DTOs.
   Cache/batching work must preserve transaction and effect barriers; measure the
   target workload and unit before claiming improvement.
5. **Keep observability honest and bounded.** Label source review, synthetic controls,
   own-executable wire, actual Core, full turn and physical-effect evidence
   separately. Usage counters can be partial; queue/retained-byte accounting is not
   RSS or spend. Preserve failed runs, exact pins and resource stops. A green helper
   suite or successful artifact upload must not stand in for the missing runtime.

### Immutable delivery references

PRs and run states can change; package links below remain pinned to the reviewed
snapshots. This document is a navigation aid, not a continuously updated status
service. No merge, auto-merge, ready-for-review conversion or deployment is implied.

[main]: https://github.com/Qweasd123tg/proteus-modules-dot/tree/206bcb9222d3e8692643cb083f809859a17f1335
[pr1]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/1
[pr2]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/2
[pr3]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/3
[pr4]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/4
[pr5]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/5
[pr6]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/6
[pr7]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/7
[pr8]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/8
[pr10]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/10
[pr11]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/11
[pr12]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/12
[pr13]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/13
[pi]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/pi-ready-steps/README.md
[letta]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/letta-evidence-blocks/README.md
[hermes]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/hermes-verify-evidence/README.md
[claude]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/fdcd5687a5a510732396d1c0bc0b9a0cc61d821a/hook/claude-command-hooks/README.md
[strict]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/056c8ded32f36352ca846d4b3ce807359e32db38/experiments/strict-pair/README.md
[skills]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/592ad5cab6ab35fa181756a42607a32a696d9ccd/examples/portable-skill-catalog/README.md
[guard]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/7d3bddaa2e49584ab04c5a78800e66e19dc182f4/examples/js-argument-replacement-guard/README.md
[guard-result]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/7d3bddaa2e49584ab04c5a78800e66e19dc182f4/examples/js-argument-replacement-guard/RUNTIME-SUPPLEMENT.md
[guard-optional]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/7d3bddaa2e49584ab04c5a78800e66e19dc182f4/examples/js-argument-replacement-guard/optional-sdk/README.md
[spans]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/b33064d33224fcc4bfbecf2df45d1a1f383da54f/examples/evidence-spans/README.md
[core-smoke]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/d6ec511febbda5b2a298f25acc7f7e607fb4a4a3/integration/core-smoke/README.md
[rmcp]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/f464bdc1ef914c617cafd43070cf04e6b15c0e7e/conformance/rmcp-lifecycle/README.md
[cache]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/5901a6013a4578d38a1e8afd65daf2a207eaed09/conformance/native-read-cache/README.md
[core-skills]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/e9a01ddf30a3240597fb427e2f29091f600e1240/conformance/core-skills/README.md
[parser]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/539cec10211e19db031f20324e67fea7bfdd4b8d/conformance/parser-compat/README.md
[append]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/354161fde438f6c898ee5dca71abd7d5efa07122/conformance/append-groups/README.md
[baseline-research]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/research/overview.md
[operator]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/8761a432b18e4843fcbda3ece42670406d850866/research/operator/README.md
[reliability]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/8761a432b18e4843fcbda3ece42670406d850866/docs/reliability/INDEX.md
[matrix]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/8761a432b18e4843fcbda3ece42670406d850866/research/operator/extension-boundaries/MATRIX.md
[guard-qualification]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/8761a432b18e4843fcbda3ece42670406d850866/research/operator/extension-boundaries/OBSERVED-GUARD-LIMITS.md
[ecosystems]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/d80b91825ff7cc59b415615df46e9f6ad363282c/research/ecosystems/INDEX.md
[ci1]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40234805399
[ci2]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40235647020
[ci3]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40245063778
[ci4]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40246734880
[ci5]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40249175569
[ci6]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40247195784
[ci7]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40248855203
[ci10]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40294522034
[ci10pr]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40296589982
[ci11]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40295024481
[ci11pr]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40296726238
[ci12]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40294703220
[ci13]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40294847167

[pr9]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/9
[pr14]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/14
[pr15]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/15
[usage]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/3af9ab5b401b6d12ff0f40947bc1ec2381da12d9/consumers/usage-attribution/README.md
[ci15]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40297813619
[ci16]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40297456519
[ci-cas-lock]: https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40297080188

[pr16]: https://github.com/Qweasd123tg/proteus-modules-dot/pull/16
[strict-host]: https://github.com/Qweasd123tg/proteus-modules-dot/blob/d4fe0b2f0a592ab07dc50085ce1cd3d490b7359b/integration/strict-host/README.md
