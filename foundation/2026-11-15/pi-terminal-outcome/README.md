# Native Pi final-generation outcome: F1/F2 candidate on PR126

This delivery package separates historical diagnostics from the final generation outcome using one shared reducer. It is a source patch for Core, not a production deployment or native Pi validation.

Dependency: apply [PR126](https://github.com/Qweasd123tg/proteus-modules-dot/pull/126)'s exact `shared-usage-projection.patch` (SHA256 c1c30727c0a76fecea815caf22bcb8ed14fdc2e6bd98ab8877027551c760866f) to Core bcbda4435534a296c707a1daa250813d692f68e1 before this patch. The dependency lives in `../benchmark-usage-projection/`.

Read REPORT.md for the contract, compatibility and limitations; source/contract reviews precede execution, RUNTIME-REVIEW.md supplements them. Two synthetic baseline controls fail at the intended behavioral assertions; candidate passes 9 new plus 6 updated PR126 tests on Python 3.12.14. No native CLI, API/LLM, install, Rust, full suite or benchmark rerun. No speed/RSS claim; production grows by 51 lines.

F4 missing usage rows, complete billing, legacy failure taxonomy and historical stored pipeline_ok results remain unresolved. Clean final generation is not complete accounting or successful postprocessing. These are known F1/F2 candidates, not new universally closed bug classes.

Raw logs, private execution paths and source snapshots are intentionally excluded. runtime-summary.json records selected results and local evidence hashes; references in review notes to omitted local artifacts describe evidence inspected during review, not files promised in this publication. REPORT's unpublished-at-authoring note is historical.
