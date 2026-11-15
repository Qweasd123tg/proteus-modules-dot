# Independent F2 instrumentation-lifecycle review

Preferred bounded direction: B, fresh stdlib probe process for each of the two affected checks. Feasible source candidate, not a runtime-approved fix. The defect is the known F2 import-order sensitivity; no historical test or graded solution was rerun.

## Contract evidence

The grader imports ledger/Store at module load, then patches os.replace or os.fsync only inside the two tests. A legal `from os import replace/fsync` during package initialization therefore retains the original callable. The release recovery contract explicitly requires os.fsync and os.replace, so patching those functions before the package's first import is a directly relevant boundary. No syscall framework or hardcoded ledger.storage/store module layout is necessary.

The current checks establish more than exception occurrence: replacement failure must leave the full disk snapshot unchanged (including foreign file and temporary-file cleanup), and reopening must recover the latest value. The fsync check requires a file sync after put and at least two file syncs plus a directory sync during compact. Preserve all these assertions and the setup ordering.

## Why B over A

A saves/restores sys.modules entries, but removing ledger* does not remove external references, cached modules outside that prefix, or import-time side effects. Existing grader-level Store/exception classes remain old objects while a newly imported package creates new ones. This can be managed for tightly controlled cases, but it adds global-state reasoning unrelated to the release contract. It is not inherently impossible; it is less clean here.

B starts with no pre-imported solution package and installs wrappers before importing the public ledger API. It avoids in-process module restoration and import-class identity mixing. The existing long_corpus preparation copies the whole grader directory, so a small private sibling probe helper can be delivered without a new packaging system. The cost is two additional interpreter invocations, which should be documented rather than described as an optimization.

## Required probe semantics

- Capture real os functions before installing wrappers. Keep wrappers installed throughout package import, setup and measured operation so directly imported aliases retain the instrumented callable.
- Replacement wrapper delegates normally until setup is complete: open, put, initial compact, second put, foreign-file creation and before-disk snapshot. Arm the injected OSError only for the tested compact. Require the intended error and then retain exact disk-equality and reopen/latest-value assertions. Do not catch arbitrary exceptions as a passing probe.
- Fsync wrapper delegates to the real fsync and classifies the real descriptor. Clear observations after import/Store.open, assert file sync for put, clear again, then preserve the original compact counts/directory assertion. Initialization or setup syncs must not satisfy the measured operation.
- Parent test must require child success and retain useful stdout/stderr traceback on failure. Invocation should use the intended interpreter and target checkout, with a finite timeout; helper/main guard should select only the requested probe. Do not run other grader tests in that child. Assertions must not be disabled by optimized execution.
- Probe functions use only public Store API and the documented os boundary. Do not patch candidate-specific internal locations, accept no-op wrappers, change mutation snapshots or weaken thresholds. A direct-import and module-qualified implementation should receive the same fault/spy behavior.

This fixes import-time alias capture in the fresh probe process, not arbitrary alternate syscall implementations or dependencies deliberately captured before the instrumentation. The documented os boundary is the scope. Full suite/case/runtime compatibility and historical scores are not established. All project/solution execution remains unperformed in this review; proposed probe controls still require exact source review before any separately authorized execution.
