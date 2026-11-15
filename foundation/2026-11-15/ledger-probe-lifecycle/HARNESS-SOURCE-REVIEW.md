# Independent synthetic harness source review

Read RUN-TARGETS.py, SHA256 `af853e5e662934995041c227bfcadd40483124fd956bbac65f963c175309b25a`. No harness/project/fixture execution performed.

The proposed scope is coherent: four baseline runs (qualified positive and direct-alias negative for each probe), six candidate style/probe positives, eight targeted negatives and four explicit -O controls, totaling 22 child invocations. These are control outcomes, not 22 successful solution/probe executions. The eight faulty fixtures intentionally exit nonzero; baseline direct-alias cases demonstrate the old observation failure.

The synthetic JSON Store is authored within the harness and is not the real Ledger or a submitted/gold solution. Its import-style substitutions cover qualified, direct and default-captured callables; format-template literal braces are escaped where required. Setup, compact/failure transitions and the negative modes plausibly reach their intended oracles. In particular unreached_fault raises before wrapper invocation; no_append_sync/one_compact_file_sync/no_directory_sync target distinct fsync requirements; swallowed failure, leaked temp, changed journal and bad reopen target their separate assertions. This is source plausibility, not observed behavior.

Baseline explicitly imports and verifies the private ledger file and preloads ledger.codec before loading the real grader definitions with minimal pytest declaration/raises stubs. Only the two selected bodies run. Candidate executes the actual io_probe __main__ using cwd private solution and the helper's explicit cwd insertion; the loader is not substituted. Parent grader subprocess delegation itself and full pytest rewriting/collection are not exercised by this candidate path.

The Python socket audit hook is installed before project/fixture execution and its construction-denial selfcheck is explicit. This is not OS isolation, network capture or proof about all possible networking mechanisms. Children use -I -B with explicit -O for four controls; this is not an inherited-PYTHONOPTIMIZE integration test. Harness timeout15 is only a verification guard, not a candidate grading timeout.

Before execution, strengthen evidence checks: pin the expected reviewed target/patch hashes before copying, and snapshot original input artifacts as well as copies if claiming source preservation. Current harness only records target digests and checks unchanged copies. Tighten baseline negative diagnostics beyond generic AssertionError: require the replacement DID NOT RAISE OSError message and the specific fsync file-membership assertion traceback. Neither issue invalidates the fixture design, but both prevent an overbroad red/green or source-identity claim.

After those bounded evidence adjustments, no additional design blocker is apparent for this explicitly authorized synthetic scope. No full grader, real Ledger correctness, native benchmark or historical regrading claim should follow.

Concurrent revision observed while recording this review: current script hashes to `37f1f0fe3344fb5ca6461c86b778d7138fa777d6e3f17d520aae5cf5766a70f8`, not the initially supplied hash. Re-read the added post-run ledger.__file__ verification and LEDGER_SOURCE output: this improves positive-path fixture identity and does not alter fixture/probe behavior. Negative exceptions exit before that post-run check, so their expected path must still be established by source/traceback. The upfront hash/original-preservation and diagnostic suggestions above remain applicable to this observed revision.

## Final pre-execution revision accepted

Independently re-read the evidence/identity changes and verified final runner SHA256 `0cd086dbf1026fa154a42caf965cf5d19a2281b4cd623a6aeaa4c7d20dfa23d6`. Fixed reviewed hashes gate original baseline grader, candidate grader/probe and patch before copying. Original sources/before/after plus patch/runner are snapshotted before and after, alongside the execution copies. Baseline diagnostics now require the specific DID NOT RAISE OSError or fsync membership assertion text. The fixture identity check runs in finally, and every control requires its private LEDGER_SOURCE marker, including intended failures.

The three evidence qualifications above are resolved. Source-acceptable for the explicitly authorized 22 synthetic child controls only. No execution has been performed by this reviewer and no runtime outcome is inferred. All limits concerning real Ledger, full pytest, inherited optimization integration, process isolation and historical scores remain.
