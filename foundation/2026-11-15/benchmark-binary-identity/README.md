# Selected binary identity: narrow source candidate

Correction of known [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85) benchmark-execution item 1, not a new finding. See [report](REPORT.md), [patch](binary-identity.patch), [final independent review](INDEPENDENT-REVIEW.md), and [pre-run review](PRE-RUN-REVIEW.md).

One production line derives argv[0] from the normalized selected binary basename, the same identity used by metadata. Baseline: 1 default-name control passes, 3 renamed-name assertions fail. Candidate: 4/4 synthetic actual adapters.prepare tests pass with mocked native loading/auth copying, Python 3.12.14. No executable, runner, benchmark, security/process-policy tests or historical score recomputation. This does not prove the executed digest. Upstream is unchanged.

Strict application and exact candidate bytes independently rechecked for publication. Composition with fixed PR126 → PR127 → PR128 is text-only, not a combined runtime gate.

## Evidence packaging

The report and independent reviews are preserved byte-for-byte, including hashes of earlier reviewed report revisions. Paths to sources/, after/, runtime/ and logs describe private verification artifacts and are not bundled. No raw logs or source snapshots are published. Public JSON files retain hashes and summarized results; these are not substitutes for an independent reproduction. run_target.py is the reviewed bounded driver; reconstruct its source copies from SOURCES.json and the patch, and expected hashes from TEST-RESULTS.json. No tests were rerun during publication.
