# Independent loader-contract review

Verdict: the proposed local helper is a justified bounded correction of the known journal-grader import omission. Proceed to exact patch/source review; no project execution performed here. Current before/after loader source was still identical at this reading, so this is design approval, not approval of an implemented diff.

Both current sites create a module with module_from_spec and execute it without registration: archiver uses archive_under_test; the existing-consumer test uses usage_under_test. Registration before exec gives module code and standard-library consumers access to its own namespace during initialization. The neighboring sampler grader already registers before execution, but its pop-on-BaseException pattern does not preserve a prior binding. It is a useful precedent, not a sufficient implementation for the explicitly requested stronger cleanup contract.

## Required local semantics

1. Create the spec/module, snapshot the prior sys.modules binding using an identity sentinel, then register the new module before exec_module.
2. On successful execution, leave the freshly loaded module registered and return it. Repeated successful calls deliberately create a new instance rather than becoming an import cache. This preserves the grader's existing fresh-execution intent; older returned function objects still belong to their older module globals.
3. On BaseException, restore the exact previous binding, including an explicit None, or remove the new entry when the name was previously absent; re-raise the original failure. A sentinel distinguishes absent from None. Catching Exception alone would miss SystemExit/KeyboardInterrupt cleanup.
4. A failure during spec/module creation before assignment should leave the existing binding untouched. No broader side-effect rollback is promised.
5. Both existing call sites should delegate, retaining their original names, paths, return extraction and grading assertions.

These are reserved grader-local names in sequential controlled loading. This is not a general concurrent import system, import-lock implementation, package-relative import redesign, rollback of dependencies imported during execution, or recovery from module code intentionally changing unrelated global state. Restoring a prior binding on failure is intentional even if failing initialization mutated its own entry. Success fresh-replacement and failure restoration are different, explicit policies.

## Planned bounded verification

Loader-only tests can safely exercise the real helper/archiver with reviewer-authored temporary modules: registration visible while executing; postponed annotations/dataclass lookup; repeated success gives a fresh module; absent/prior module/prior None restored after failure; BaseException cleanup; harmless ordinary archive function extraction. The existing-consumer call-site delegation can be checked statically without running its grading body. A decorator-only pytest stub and harmless journal stub may support loading the grader definitions without invoking grader tests. Stub setup/teardown must restore prior sys.modules and sys.path state and should not be described as executing the genuine grading suite. Do not run graded solutions, native commands or unrelated test bodies.

Source snapshot hashes independently read:
- journal grader: `029666fba8b8c43f302bff44951778a689dde42a851f5d5af558b7694c455f8e`
- sampler grader: `a16bd0408b73f97266cdf731a7bf6671415a7c9d98489f1497b8da3949d08c93`

Core baseline and six-source catalog identity are coordinator provenance: bcbda4435534a296c707a1daa250813d692f68e1. No benchmark regrading or historical-score claim follows from this contract review.
