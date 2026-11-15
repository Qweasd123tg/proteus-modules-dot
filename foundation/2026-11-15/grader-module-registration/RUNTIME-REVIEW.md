# Independent targeted-runtime evidence review

Verdict: saved evidence supports two expected baseline loader errors and six passing candidate synthetic controls. No blocking discrepancy found. I read PREPARATION, RUNS, RESULT, both stderr logs and RUN-TARGETS.py; I did not rerun tests or import project code. Independent execution was limited to file/JSON/hash verification.

## Identity and observed results

Core baseline: bcbda4435534a296c707a1daa250813d692f68e1. Final patch independently hashed as `cfddbd8a4917b89e5a10b7617f4f80c997d7d6467649b204fa21a7d2c8b897bd`.

INPUTS-BEFORE and INPUTS-AFTER match. Recomputed current hashes match every manifest entry: before 7 files, after 9, sources 7, baseline copy 8, candidate copy 9. Candidate equals reviewed after; baseline equals before plus only the exact new test module. All four stdout/stderr hashes match RUNS. Preparation records successful text apply check/application and seven Git blob identity checks; those operations were not rerun by me.

The two baseline traces reach the real original archive and measurements exec_module sites respectively. Both fail in dataclasses._is_type at sys.modules.get(cls.__module__).__dict__, with AttributeError on NoneType. They are the expected target import-time loader errors, not assertion failures, missing dependencies or generic unrelated process failures. Baseline exit 1 reports errors=2.

Candidate exit 0 reports six tests OK: archive postponed annotations/dataclass, actual existing consumer body with trivial fixtures, sampler registration positive control, absent-entry exception cleanup, previous module/None restoration, and fresh successful reload. ValueError/SystemExit combinations are subcases, not additional counted test methods. This is six candidate passes, not eight passes or the full pytest grader suite.

## Scope and preservation

Recorded interpreter is Python 3.12.14, with -B -E -S, separate copies, clean explicit environment and private HOME/TMPDIR. The wrapper runs exactly two project commands: two named baseline methods and the six-method candidate module. It installs nothing. Recorded temporary directories are empty afterward. No extra OS/network namespace is claimed.

The test source uses runpy to load real grader definitions with a decorator-only pytest stub; it explicitly imports the unchanged private copied journal and checks its __file__ before runpy. Loader implementations are not mocked. One existing consumer test body runs against reviewer-authored trivial archive/measurements modules plus actual journal text helpers. That is not a submitted solution, valid archive implementation, CLI execution or full grader evaluation. Other grader bodies remain idle. Inspection of selected paths supports no native benchmark/API/LLM/Rust invocation; this is not a network capture or whole-system tracing claim.

Manifest equality establishes preservation of the listed source and copy trees, not the entire filesystem. No historical benchmark dataset or scores were recomputed. The results establish the bounded loader behavior and failure cleanup for these controlled names/modules, not general concurrent import correctness, package loading, dependency rollback or full grader compatibility. The sampler's existing weaker exception-cleanup policy is not changed by this patch.

## Evidence hashes

- RUN-TARGETS.py: `6ffca9549fdfe13905b7da5d5da96bbcfadfe2914bdf69993908d352ca6ed8fe`
- runtime/RUNS.json: `ed708d0dbe24715f2f6fc0481f941b84d3a45f07a0c38b42e5630b775c3daf2f`
- runtime/RESULT.json: `f53b841d3174f713217a9b9f7f90238a4ac3e209b1a5d00f7ae6c58dfac65280`

This supplements the pre-execution SOURCE-REVIEW; its historical NOT RUN statements describe that earlier stage.
