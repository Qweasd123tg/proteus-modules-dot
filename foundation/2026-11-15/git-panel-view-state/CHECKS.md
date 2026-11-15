# Checks actually performed

2026-11-15. Source-only, not compiled or runtime-qualified.

- Start/end main refs match REFS.json; 19 source/doc files match pinned Git
  blob SHA-1 and SHA-256. Provenance trees were untruncated.
- Two production files changed: main.rs +12/-4, panel.rs +4/-4, total +16/-8.
  tests.rs +139/-8: eight existing direct panel calls adapted and six tests
  added with small helpers in the same existing test module.
- patch --batch --fuzz=0 applied all three files in an owned copy; cmp verified
  byte identity with candidate. Forward and reverse git apply --check
  --whitespace=error-all returned exit 0.
- git diff --no-index --numstat used for line counts; difference exit 1 is
  expected and is not a test failure or a behavioral pass.
- Report/README relative links resolve. Candidate/report/README have no
  trailing whitespace. Existing top-level Git caller references inspected.
- Python stdlib only wrote/copied text, generated a diff and checked hashes.
  It did not import/execute project code or run a substitute behavior model.
- No cargo/rustc in PATH, no installation, rustfmt, compiler, tests, SDK wire,
  HTTP fixture, native UI, real repository or Git write operation ran.
- Six proposed new tests and the existing suite remain NOT RUN. Historical
  results are background only, not current baseline/candidate qualification.
- Independent source review covered design, exact patch, proposed assertions
  and final prose. No upstream or production repository was changed.
