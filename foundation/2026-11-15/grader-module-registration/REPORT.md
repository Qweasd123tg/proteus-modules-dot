# Candidate: correct module registration at the journal grader boundary

## Status, source and dedup

This is a bounded fix candidate for **known benchmark-design F1/P2 from PR85**, not a new finding or a new real benchmark. Core `bcbda4435534a296c707a1daa250813d692f68e1` still has the omission. The candidate is isolated from upstream production and has not regraded any user's saved solution.

Start/end refs agree: Core `bcbda4435534a296c707a1daa250813d692f68e1`, Modules `c035142558f0fca43e9772fc0e50ca293abf1531`, delivery `ea4ab968cf7b988fb87d4a14314ba84ba72d24cb` after PR129. Seven read-only Core source blobs are Git-blob verified in SOURCES/READ-VERIFICATION. No changed-file overlap or dependency on PR126–129 candidates: this patch changes the journal fixture grader and adds a standalone loader test/document, leaving the common coding-harness README untouched. Those prior synthetic tests were not rerun here, and their limitations remain.

Patch `grader-module-registration.patch` SHA256: `cfddbd8a4917b89e5a10b7617f4f80c997d7d6467649b204fa21a7d2c8b897bd`.

## One missing loader invariant, two affected paths

The journal grader uses `module_from_spec` followed directly by `exec_module` at two sites: the archive function loader and its existing-measurements consumer check. Neither registers the module in `sys.modules`. Ordinary standard-library dataclasses with postponed annotations consult their defining module during class construction; they fail before the intended function can run. The task permits standard Python implementations and does not forbid this representation.

The nearby sampler grader already registers before execution. Instead of creating a shared packaging/import framework, the candidate reuses that idiom in one small journal-local helper and routes both existing sites through it. It strengthens the failure case to preserve an existing binding rather than blindly removing it:

- Snapshot the prior `sys.modules[name]` binding with an identity sentinel, distinguishing absence from explicit `None`.
- Register the fresh module before executing it, so initialization and dataclass lookup see the current module namespace.
- Success returns and leaves the fresh module registered. Each successful call still freshly executes source, as the prior grader did; this is not import-cache reuse. Prior module objects are not modified by the loader itself.
- On `BaseException`, restore the exact previous binding or remove the new binding if previously absent, then re-raise the original exception. This includes `SystemExit`, not just ordinary exceptions.

The archive function extraction, module names, paths, and actual grading assertions remain unchanged. Both loader sites now use the same rule rather than separate incomplete import sequences. This is a consequential compatibility correction, not a cosmetic shortening: the grader file grows **170 → 183 lines (+13)**. New controls are 141 lines, documentation 20 lines. No LOC-reduction/performance claim is made.

`ASSERTION-PRESERVATION.json` records a non-executing AST comparison: all assertion ASTs are identical, and existing function ASTs outside the two affected sites are unchanged. This is evidence of unchanged assertions, not proof of complete grader equivalence under all possible modules.

## Actual bounded execution

Independent source/contract reviews preceded execution. The driver staged two separate copies: raw Core plus only the new test module, and raw Core plus the exact candidate patch. `git apply --check --whitespace=error` and application succeeded; the applied candidate matched reviewed `after/` byte-for-byte. Source and copy hashes match before/after execution.

Interpreter: **Python 3.12.14**, `-B -E -S`, explicit clean environment, private temporary HOME/TMPDIR. No dependencies installed. Existing platform sandbox and separate copies are used; no extra OS/network namespace or tracing guarantee is claimed. The documented grader Python 3.13.9 and full case assembly from pinned repository fixture revision `879183f3853ce469346b19634e9440c6d7d7cd0f` were not exercised; these controls use the explicitly catalogued current Core journal helpers.

| Target | Observed result |
|---|---|
| Raw Core: archive dataclass control | Expected loader error inside `dataclasses`: absent module namespace, `AttributeError: 'NoneType' object has no attribute '__dict__'`. |
| Raw Core: measurements consumer dataclass control | The same expected loader error at the second real import site. |
| Exact candidate: new module's six controls | **6 passed**, including both formerly failing paths. |

The baseline result is **two errors**, not two assertion failures or infrastructure success. Their saved tracebacks go through the exact Core loader and the standard-library dataclass namespace lookup. They are the target defect. Candidate exit is 0/OK.

The six controls cover both dataclass load paths; repeated successful fresh loading with old returned functions retained; registration visible during initialization; original exception identity; absent/prior-module/prior-None cleanup for `ValueError` and `SystemExit`; and a positive control using the unchanged sampler loader. Subcases are not counted as additional independent test methods.

These tests use the real grader function definitions, loaded with `runpy`. Only pytest's declaration decorator is stubbed to avoid requiring pytest. The exact copied journal module is imported and its `__file__` verified before the grader definitions load; the grader cannot accidentally substitute an ambient `/app` journal. Context managers restore test `sys.modules` and `sys.path` state.

The measurements control calls one actual existing consumer test body with **our trivial synthetic archive and measurements implementations** and unchanged journal text/digest helpers. All other archive test bodies remain idle. This is explicitly not evidence that the synthetic archive satisfies the task. No original/reference/submitted solution, full pytest grading suite, archive CLI, native process, provider/API, Rust compiler, or real benchmark was run. The historical 37-test result described by PR85 was not repeated here.

## Compatibility and remaining boundaries

- Success deliberately replaces the reserved grader-name binding with the current freshly loaded module; failure restores the prior binding. These are different policies. Prior object attributes remain unchanged unless loaded code itself changes them.
- Cleanup covers this module binding only. It does not roll back arbitrary module side effects or dependencies imported during initialization, and does not implement concurrent import locking or package-relative import semantics. The grader uses controlled reserved names sequentially.
- The unchanged sampler loader is a registration positive control, not a claim that its own failure cleanup preserves previous bindings. This candidate does not expand to that independent contract.
- A change to the hidden grader changes its recorded grader hash for future preparations. Existing corpus preparation already copies the grader directory; no additional packaging hook is needed. Saved case artifacts and saved scores were not silently mutated or regraded.
- No affected historical run is identified. Regrading would require its original workspace, detailed traceback and separately recorded new grader revision. Existing successful benchmark scores are not declared incorrect.
- Known benchmark-design F2/F3, PR126–128 accounting limits and PR129 phase-interval limits are outside this fix. No previously excluded security/process-authority direction was investigated.

## Evidence

`CONTRACT-REVIEW.md`, `SOURCE-REVIEW.md`, and `RUNTIME-REVIEW.md` distinguish initial design, exact-source acceptance and independent review of actual commands/logs/hashes. `runtime/` contains preparation, source/copy manifests, commands/environment/timestamps, both stderr/stdout pairs and RESULT. `RUN-TARGETS.py` reproduces only the bounded controls in a new runtime directory and refuses to overwrite an existing evidence directory.

The prior design report is retained as historical context only; its pytest/live-run numbers and other findings are not new execution evidence. This candidate establishes tested loader compatibility under the stated synthetic controls, not full project or production readiness.
