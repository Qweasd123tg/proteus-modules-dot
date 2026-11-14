# Benchmark design audit: oracle validity and paired conditions

## Scope

- Audited Core/main: `89997df995df7c39b713e16aba216ecb19c8f497`; remote main rechecked at start/end and unchanged.
- Isolated checkout `/workspace/shared/benchmark-design-audit`, clean production working tree. The repository fixture pin `879183f3853ce469346b19634e9440c6d7d7cd0f` was fetched read-only because the initial checkout was shallow.
- Focus: public/long task preparation, hidden graders, solution acceptance and comparable experimental conditions. The separate accounting/recovery findings are not repeated here.
- No model/provider call, credentials, GitHub publication, source modification, or rewriting of historical results.
- These are benchmark oracle/validation defects, **not evidence that Proteus runtime or the user's successful benchmark scores are wrong**.

## Verification and boundaries

The actual 37-test journal grader and 34-test ledger grader were run against disposable copies of the repository's gold implementations. All candidate changes are small standard Python refactors of those gold implementations; no submitted unknown code was run.

Full bubblewrap execution is unavailable here: `bwrap: loopback: Failed to create NETLINK_ROUTE socket: Operation not permitted`. Therefore the tests were executed locally, mapping only their hardcoded `/app` location to a disposable directory. Test bodies and requirements stayed unchanged for the failing runs. Control runs that correct the oracle are explicitly separate. This proves the Python loader/spy defects, not a new full live benchmark run.

Verification used pytest 8.4.1, Python 3.13.5 and also Python 3.12. The benchmark README pins 3.13.9, which was not installed or tested here. Both available Python versions reproduce the same results.

| Scenario | Result |
|---|---:|
| journal original gold + existing grader | 37 passed |
| journal equivalent dataclass gold + existing grader | 37 failed at module load |
| same dataclass solution + corrected disposable loader | 37 passed |
| ledger original gold + existing grader | 34 passed |
| ledger equivalent OS function aliases + public suite | 6 passed |
| same aliases + existing hidden grader | 32 passed, 2 false failures |
| same aliases + spies at actual lookup sites | 34 passed |
| mixed `high`/`low` synthetic pair through actual runner gate and long report | accepted as complete; top-level declares `high` |
| desired-behavior regression suite | 3 failures against unchanged audited code |

The probe scripts assert the observed defect and complete successfully. They are diagnostics, not fixes. `test_expected_behavior.py` expresses the desired behavior and intentionally fails three tests.

## F1. P2: journal-segments rejects ordinary dataclass-based solutions before running them

Source: [journal-segments grader, lines 16–20](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/long_repo_fixtures/journal-segments/grader/test_outputs.py#L16-L20).

`archiver()` constructs an importlib module and immediately executes it, without registering `sys.modules[spec.name]`. A normal `@dataclass` using postponed annotations resolves annotation information through that registration. The loader fails with `AttributeError: 'NoneType' object has no attribute '__dict__'` before `archive()` can execute.

Reproduction changes only the gold archive implementation's segment metadata representation from `dict(...)` to an ordinary `Segment` dataclass and `asdict(...)`, with `from __future__ import annotations`. The output manifest and operation behavior are the same. Ordinary Python import succeeds. All 37 existing grader tests nevertheless fail with the current loader; all 37 pass after registering the module and cleaning the registration on failed execution.

This is a false negative caused by a legal implementation choice that the prompt does not forbid. The sampler grader already contains the needed registration pattern, and runner_selfcheck already tests this condition for sampler but not journal.

Fix direction: apply the same safe module registration used by sampler to the journal loader, add a loader regression using a standard dataclass, and regrade any affected saved workspaces without rerunning the model. Do not claim an affected historical run until its original source/error has been inspected.

Evidence: `probe_grader_local.py`, `probe_grader_python313.log`, `journal-*-local.json`; original and corrected disposable graders are separately staged.

## F2. P2: ledger-recovery's syscall probes reject correct direct imports

Source: [ledger grader, lines 158–185](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/long_cases/ledger-recovery/grader/test_outputs.py#L158-L185), together with top-level imports of `ledger` and `ledger.codec` at lines 11–13.

The suite imports the solution first and later patches `os.replace` and `os.fsync`. A normal implementation may use `from os import fsync, replace`; its cached function references are not affected by replacing attributes of `os` afterward.

Reproduction only refactors the gold implementation in `storage.py`, `store.py`, and `migrate.py` to use direct imports. Every real filesystem operation is still the same original OS function, with the same arguments and ordering. All six public tests pass, but the hidden grader emits:

- `test_failed_snapshot_replace_preserves_all_previous_bytes`: `DID NOT RAISE OSError`, because the fault was never injected into the called function.
- `test_append_and_snapshot_fsync`: `assert 'file' in []`, because the spy misses the real fsync calls.

The result is 32/34 instead of 34/34 despite semantic equivalence. For this known reference only, moving the spies to `ledger.storage.replace`, `ledger.storage.fsync`, and `ledger.store.fsync` restores 34/34 without changing the solution. Hardcoding these lookup sites is **not** a general benchmark fix: arbitrary valid implementations may organize their files differently.

Fix direction: inject fault/recording wrappers before importing a fresh solution in an isolated subprocess, or use an implementation-independent filesystem/syscall boundary. Keep the mutation-preservation assertions. Test both module-qualified and directly imported OS functions. Do not require an undocumented import style.

Evidence: `probe_ledger_local.py`, `probe_ledger_python313.log`, `ledger-*-local.json`.

## F3. P3: long_report accepts differing reasoning effort as a paired Flash/high experiment

Sources: [long_report.build, lines 415–425](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/long_report.py#L415-L425), [hardcoded top-level conditions, lines 475–485](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/long_report.py#L475-L485).

Each runner verifies its own requested model/effort. The long report verifies common prompt/repository hashes, but does not require a common actual model/effort or agreement with its declared conditions. Summary/pair grouping is only by arm and case. The top-level report and Markdown state Flash/high unconditionally.

A synthetic Native Pi/high row and Proteus Pi/low row each pass the actual `runner.check_pipeline`; their prompt/repository hashes match. `long_report.build()` accepts both, marks the report complete and the comparison paired, computes deltas, and emits `effort: high` for the overall experiment. No source/result mutation is needed beyond constructing the ordinary recorded-result inputs.

This is a validation gap for misassembled future runs, not a demonstrated historical bias. The saved `2026-11-11-deepseek-long.json` has **40/40 rows with Flash/high**, so this finding does not invalidate that report.

Fix direction: validate expected model and effort across selected trials before computing paired comparisons; either reject differing conditions or group and label them as separate experiments. Derive report labels from validated conditions rather than folder naming/hardcoded strings. Preserve per-row diagnostics for rejected inputs.

Evidence: `probe_comparability.py`, `mixed-effort-report.json`, `mixed-effort-report.md`, `probe_comparability.log`.

## Historical-result boundary

The saved long summary was inspected. Four non-Codex journal first attempts list only the explicit truncated-legacy-line failure, not this dataclass loader failure. The Codex journal first attempt has all 37 failures and a recorded output-limit failure, but the raw workspace and grader traceback are absent here, so no cause is assigned to its failures. Ledger's successful native/profile rows and its recorded cycle failure do not establish an alias-spy effect. Regrading the user's runs requires their actual saved workspaces and original detailed grading output.

## Reproduce

From this environment:

```sh
export PYTHONPATH=/workspace/shared/benchmark-design-evidence/venv/lib/python3.12/site-packages
export PYTHONDONTWRITEBYTECODE=1
/usr/bin/python3 /workspace/shared/benchmark-design-evidence/probe_grader_local.py
/usr/bin/python3 /workspace/shared/benchmark-design-evidence/probe_ledger_local.py
/usr/bin/python3 /workspace/shared/benchmark-design-evidence/probe_comparability.py
/usr/bin/python3 /workspace/shared/benchmark-design-evidence/test_expected_behavior.py
```

The last command should report 3 failures against this audited revision. Pure-Python pytest dependencies are from the temporary local venv; this does not install packages into the repository or system Python.
