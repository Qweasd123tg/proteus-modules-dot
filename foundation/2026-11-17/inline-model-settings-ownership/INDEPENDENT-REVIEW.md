# Independent review: partial inline model-settings source ownership

Date: 2026-11-17. Verdict: **PASS for publication of the bounded repair and its
scoped native evidence.** No blocking source defect or misleading pass count was
found in the reviewed material. This is not upstream or production acceptance.

## Exact reviewed patch identities

| Artifact | SHA-256 |
|---|---|
| `inline-settings-source-owner.patch` | `be236f06a20c9f5275d4f42df8587d105c4f09aa2748b9cd7d87d2d07e0d1c15` |
| `inline-settings-regression.patch` | `aa163f3954bbb59b2ff5bfcfa81c058b37d630cfe800be896d1afc74bdb53ed0` |
| `inline-settings-on-PR167-PR171.patch` | `e920189371b1b39c88ebc41d68aed5798ab9cccce63862d9c7d4d295023435db` |

Core baseline: `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`.
Standalone source commit: `58959241091cf01428a8a69df8904f643dbc13a4`;
its immediate parent is exactly that baseline.

## Source review

I read the exact three patches, their surrounding writer/loader/serialization
code, both selected existing test modules, REPORT.md and the three validation
JSON documents.

The correction is limited to an inline selection whose effective
`module_config.model` map equals the loaded baseline. TOML retains the raw
selected child's authored model-settings item before replacing its managed
module-config section. JSON captures the raw child value before replacing that
section. Both formats preserve the original partial local ownership rather than
serialize the inherited effective entries. Absence stays absent; local entries
are not removed or rewritten from parent state.

An intentional change of the effective model-settings map makes the equality
predicate false and retains the previous serialization path. Non-inline targets
are excluded by the selection check. Missing-source handling, other managed
fields, provider definitions and alias normalization are not altered. These are
source-review conclusions; not every one is a new runtime regression case.

The proposed test checks the concrete defect, not just implementation shape: an
unrelated tools-list save must retain the child's local provider settings without
materializing another provider's inherited settings, and a subsequent parent
update must remain visible. Its accumulated diagnostics cover both formats.

## Checks independently performed

No project executable, compiler, test runner or process fixture was run during
this independent review.

- Computed all three exact patch hashes and compared every declared standalone
  and composed source hash in VALIDATION.json with the actual files.
- Applied the standalone production and regression patches strictly to isolated
  copies of the exact baseline files, compared both resulting files byte-for-byte
  with the committed standalone source, and reversed them to exact original bytes.
- Independently built the raw #167-production + #167-test + #171 source from the
  exact baseline using strict patch application. Applied the explicit composed
  variant, compared all five resulting files with the composed checkout, then
  reversed it to exact raw-prior bytes.
- Confirmed the composed variant leaves the prior loading.rs, models.rs and
  models_tests.rs byte-identical. The additional changes in prior #167 material
  are the two described formatting-only long-line adjustments.
- Confirmed both checkouts retain the baseline Cargo.lock unchanged.
- Read the native outputs: final baseline regression FAIL with capture and
  blocked-parent-update diagnostics in both TOML and JSON; standalone
  model_names 5 PASS and inline_roles 5 PASS; composed new regression 1 PASS.
  The latter is the same regression repeated on a different source stack,
  not an eleventh distinct test. Existing dead_code warnings remain explicit.

## Composition and remaining limits

The original standalone patch's JSON context conflicts with #167; the recorded
failure is not silently reclassified as a successful composition. The explicit
variant correctly targets the **raw original #167/#171 patch stack**. It is an
alternative to the standalone pair, not an extra patch to apply alongside them.
This review does not establish applicability to the separately formatted combined
candidate published in #175 or to an arbitrary newer upstream revision.

Only the new regression was rerun in the composed lane. The full #167/#171 suite
was not rerun after this source-ownership change, so the report correctly avoids
claiming full combined-stack acceptance. Previously materialized overrides remain
untouched; concurrent source edits, file-include deletion semantics, actual
app-server publication/watcher behavior, process/HTTP/UI paths, hosted CI and
performance remain outside this qualification.

Source correctness within the stated boundary, the exact artifact identities and
the reported scoped evidence are sufficient to publish this repair candidate.
