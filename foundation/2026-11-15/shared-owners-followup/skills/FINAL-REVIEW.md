# Supplemental final review: lock-only shared-source freeze

Final normalized patch: SHA256
`571def00d3461f9a1a67e72b579f035cf8667b25713a7067f97d254cc0a46749`.
Validation driver: SHA256
`a8cf23735609519ba73385da2fecaa7525b8bc8c4c11a90eadc030d74fdee696`.

**The specific blocker in this review's earlier REVIEW.md is resolved.**
The exact `lock_only.sh` post-resolution Python fragment now checks the
`shared_ci` owner root as well as the harness and portable module. The
Cargo.lock exception remains exclusive to the harness. The affected CODE
hashes and recorded v2 manifest match the actual final candidate. The
misleading standalone gate header was corrected.

I reviewed the final validation delta before execution and then inspected
the actual `checks-v2/post-resolution-*` stdout/stderr and recorded exits:

- Unchanged inputs: exit 0.
- Modified shared verifier: exit 1, specifically identifying
  `('shared_ci', 'verify_results.py')`.
- Only harness Cargo.lock modified: exit 0.

These checks execute the exact Python fragment against isolated copied
inputs, not the shell lock-resolution gate, Cargo, a Rust probe or product.
The main source manifest also still rejects changed/missing shared inputs.

The complete recorded v2 set is 37 expected outcomes: 27 zero exits and 10
intentional rejection exits. The suite total remains 60 method executions
across 15 unique methods, two revisions and two lanes. The three added
post-resolution checks are separate outcomes, not three additional suite
methods or proof of Core execution. I checked the actual final freeze and
manifest against candidate bytes rather than adopting a stale log label.

No remaining source-level blocker was found in this narrow second review.
The broader package/evidence review is separate. The compatibility caveat
remains material: current-core-skills now requires repository layout and
its sibling shared owner; standalone copies and the four removed private
script entrypoints are not preserved. This is acceptable only within the
explicit repo-layout boundary, not as universal behavior equivalence.

No Cargo/Rust compilation, full CI/envelope, actual Core probe, native UI or
performance acceptance is asserted. This review performed no remote writes
and does not establish publication or runtime integration.
