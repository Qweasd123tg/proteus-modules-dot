# Validation status — runtime PENDING

**All 33 authored Rust cases remain unrun at this initial CI-validation commit.**
No compilation, actual SDK runtime result or actual Core integration is claimed.

Source preparation completed: offline lockfile resolution (69 packages), locked
no-deps metadata, final Rust formatting/check, source review and eight authored
Python evidence-verifier controls. The latter operate on authored log strings;
they are not Rust or MCP runtime tests. Prior local failed controls were corrected
before this source freeze; no failed result was relabeled as success.

`CODE.sha256` and `validation/source-hashes.json` identify the reviewed source/gate
bytes. The CI workflow executes `bash ci/run.sh` and publishes raw evidence even
on failure. It requires a fresh artifact directory, unchanged pre/post source
hashes, all 33 exact named Rust cases, suite totals 2/12/19 (plus two empty unit
harnesses), and zero ignored, failed, measured or filtered cases. Full compilation
and runtime validation are pending the workflow result for this exact commit.

The scoped gate covers the actual pinned rmcp client and an authored child
responder, not Proteus Core's custom transport/config/registry, real MCP servers,
external models, full protocol compatibility or process-effect settlement.
A completed workflow must be checked before this package is called runtime-tested.
