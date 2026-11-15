# Independent source review: fresh ledger OS probes

Patch independently hashed: `de420f280d17c5f943e68a0250316050bc6a766cf69a94e2d9b222b5d73838fb`.

Verdict: the proposed before-import instrumentation lifecycle is sound for the documented os.replace/os.fsync contract. One small qualification gap should be closed before describing the probes as unconditionally preserving assertions: ordinary child assertions can be disabled by inherited Python optimization (below). No project imports, compilation, tests, probe or solution execution occurred in this review.

The child uses the same interpreter and explicit solution cwd. Its package import occurs inside the patch context, after the real OS function is captured, so module-qualified, direct-import and default-argument captures observe the wrapper. The parent grader's earlier ledger import is not inherited as Python module state by this fresh interpreter. No candidate-specific module paths are patched. Whole-grader directory copying already supplies io_probe.py.

Replacement setup delegates to real os.replace; arming occurs only after the original baseline setup and byte snapshot. The tested compact must propagate OSError, an injected-call witness must be nonempty, the complete disk snapshot (excluding .lock as before) must remain equal, and reopen must yield [2]. The probe does not require identity of the propagated OSError, matching the original broad exception-type assertion. The wrapper stays armed through reopen whereas the old patch scope ended before reopen; the release contract explicitly says open/read do not mutate disk, so this is consistent but not exact scope equivalence.

Fsync delegates to the real function, classifies actual descriptors, clears import/open observations before put and clears again before compact. File-at-append and >=2-file-plus-directory-at-compact assertions remain. No-op sync, suppressed failure or leaked temporary files should still fail the intended controls. These expectations have not executed against any implementation.

Parent names remain unchanged and require zero child return code with stdout/stderr available on failure. No local timeout was added, intentionally retaining the existing overall grader budget rather than asserting new process-lifetime behavior. Extra interpreter overhead and failure diagnostics differ from in-process tests; no performance or full-suite equivalence follows.

## Required qualification / small hardening

The old assertions run in pytest's rewritten test module. The new io_probe.py is an ordinary script, and subprocess inherits environment. Under PYTHONOPTIMIZE, ordinary assert statements disappear, potentially letting fsync/mutation checks report success. No such active-environment incident is established here, but this is a direct portability gap introduced by moving assertions to a child script. Prefer explicit conditional AssertionError checks for these few requirements (or at least fail closed when __debug__ is false). This needs no framework or change to grading thresholds. A final source revision can resolve it without running anything.

Hashes read:
- io_probe.py: `6390978388e0828630a81f9343391c82d9bd9e65c1173501790f7df1e4f9c2f7`
- test_outputs.py: `f11a9cea7075697015319fc49a88b8da7c19f75ec01d1e6e30a58780c56a2a59`
- README.md: `20e9033c05f15e62a601a501cb06f9086899c0519f99469709a1f3b3fd5a2556`

Full qualified/direct/default-capture controls, deliberately missing-sync/cleanup implementations and the actual grader remain NOT RUN. This is a known F2 correction candidate, not a new incident or historical regrade.

## Final revision: qualification gap closed

Independently re-read final io_probe.py and verified final patch SHA256 `10434bcde9866f02068b62019bf113bec9d509f17be059e4155f8281f6949869`; helper SHA256 `9a61d18e41cd104f0db3593d5a7bb007ce902d0fa7beb90e4a3a0820df90b8bc`. These supersede the initial hashes above.

All five child assert requirements are now explicit if/raise checks, so Python optimization does not disable these oracles. The expected-OSError else/raise remains explicit. Injection evidence is a boolean. After the tested failure, armed becomes false before leaving the patch context; disk comparison and reopen occur afterward as in the original stage ordering. Previously captured wrapper aliases therefore delegate to real replace during reopen as well. The earlier assertion and armed-reopen qualifications are resolved.

Final verdict: source-acceptable bounded candidate; no remaining source blocker found within the reviewed contract. Omitting a new per-probe timeout does not block this source candidate: it intentionally avoids adding a new local pass/fail time budget, retaining reliance on the existing overall grader budget. This does not establish equivalent elapsed performance or any new process-lifecycle/isolation guarantee. No project/runtime execution or targeted/full-grader PASS is claimed.
