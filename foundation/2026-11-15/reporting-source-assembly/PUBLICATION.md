# Publication boundary

This package publishes the exact reviewed combined patch and report/review metadata. Raw stdout/stderr, environment and application logs, private execution paths, source snapshots, runtime copies and local-only test controllers are intentionally excluded. References to those items in REPORT/REVIEW describe evidence inspected locally, not files supplied by this publication. Driver hashes identify the reviewed local execution; reconstructing that controller is not required to apply the patch.

The original source, pre-run and runtime reviews are retained verbatim. The publisher independently verified the original 77-entry manifest, and repeated zero-fuzz/no-offset combined apply and reverse in a disposable copy: both checked order results were byte-identical and reversal recovered the baseline. No project tests were rerun during publication.

43 unique candidate methods passed; nine baseline executions produced seven expected assertion failures and two expected loader errors. 52 executions is not 52 passes. All execution is bounded Python synthetic/mock evidence, not benchmark/API/packager/install/Rust qualification. Historical scores and upstream are unchanged.

The combined patch replaces the selected originals #126→#127→#128 plus #129/#130/#143 on the exact Core base. Do not apply it on top of them. #141 is excluded.
