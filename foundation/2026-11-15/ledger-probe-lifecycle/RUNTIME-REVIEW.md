# Independent synthetic runtime evidence review

Verdict: recorded evidence supports all 22 expected control outcomes, not 22 successful probe executions or real Ledger qualification. No rerun/import of project code was performed by this reviewer. Read RESULT, actual stdout/stderr for all cases, full baseline-negative tracebacks, runner source and top-level run output. Independent execution was limited to stdlib file/JSON/hash checks.

## Observed matrix

Python 3.12.14 executed four baseline invocations: two qualified-import positives exit 0, two direct-alias negatives exit 1. The actual baseline test bodies fail at DID NOT RAISE OSError and the file-in-fsync-kinds assertion respectively, not unrelated fixture imports.

Eighteen candidate invocations comprise six style/probe positives, eight targeted negative fixtures, and four explicit -O controls. Eight candidate invocations exit 0 and ten intentionally exit 1. Qualified/direct/default-captured good fixtures pass both probes. Negatives hit the intended messages for missing append sync, insufficient compact file sync, missing directory sync, swallowed replacement failure, leaked temporary file, changed prior bytes, incorrect reopened value and unreached injected fault. Optimized good fixtures pass and optimized missing-sync/leaked-file fixtures reject. These are expected red/green control outcomes, with overlapping oracle coverage, not independent application workloads.

Every case stdout reports NETWORK_GUARD=blocked and the exact private synthetic ledger path. Failure cases also reach the finally-path identity check. All fixture and target hashes independently match RESULT entries. The synthetic Store is the harness-authored JSON implementation, not gold, submitted or real Ledger storage.

## Identity/preservation

Independently verified:
- runner SHA256 `0cd086dbf1026fa154a42caf965cf5d19a2281b4cd623a6aeaa4c7d20dfa23d6`;
- runtime/RESULT.json SHA256 `cc16c13595f56596ab3919e51472792dc46ebe865f9fd719406518d088a941f5`;
- original-before/after hash maps identical and all 17 current original entries match;
- copy-before/after maps identical and all four current execution-copy entries match;
- all 22 target and fixture hashes match current files.

The approved runner checks the fixed baseline/candidate target and patch hashes before copying. This preservation claim covers those listed source/artifact/copy files, not the entire filesystem. No historical scores or original benchmark datasets were used or regenerated.

## Limits

The real two baseline function bodies execute via runpy with a minimal pytest stub; candidate io_probe executes through its actual __main__. The new parent test_outputs.run_io_probe wrapper, pytest collection/assertion rewriting, full case packaging and full grader are not integration-tested here. Neither Python 3.13.9 nor real Ledger/reference/public-suite compatibility is established by the Python 3.12.14 synthetic controls.

Children use -I -B and four explicitly add -O. This confirms the selected explicit child oracles in optimized mode, not full inherited-PYTHONOPTIMIZE environment compatibility. The 15-second timeout belongs to the verification harness only and does not modify the candidate's overall-grader-budget contract.

The socket audit guard is installed before fixture/project code and blocks its explicit socket-construction selfcheck. It is a Python-level guard, not an OS network namespace, sandbox guarantee or network capture. No native application/API/LLM/Rust activity appears in inspected selected paths. Process-lifecycle/cleanup and other excluded boundaries were not investigated.

The original source-only REPORT and source reviews describe their earlier stage; this document supplements them with bounded actual evidence, not a broader runtime endorsement.
