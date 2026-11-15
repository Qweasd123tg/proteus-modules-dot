# Checks and non-checks

Actual checks:
- Current refs: Desktop 7eaf70c; Extensions f82b3ad; delivery 21229e4 (#148).
- Source/doc Git blob checks against the pinned Desktop tree: 19 files.
- Historical report and minimal source fixture verified separately against delivery-tree blob IDs.
- Production diff measurement: tree.rs +37/-0. Test-module inclusion +1; new proposed test file 224 lines, eight tests.
- Forward git apply --check --whitespace=error-all: exit 0.
- patch --batch --fuzz=0 -p1 in isolated copy: exit 0, three files.
- Reverse git apply --check --whitespace=error-all: exit 0.
- Three candidate/application byte comparisons: exact.
- Independent design and exact source patch/tests review: no blockers found.

Not done:
- Rust/rustfmt/Cargo: unavailable in PATH, not installed.
- New/existing tests: NOT COMPILED / NOT RUN. No baseline-red/candidate-green.
- No Python behavioral substitute, operation fuzzing, native window, GUI interaction, actual preference save/load/restart, installation or external API/provider call.
- Fixture geometry/idempotence expectations are proposed and bounded; no universal geometry/floating-point guarantee.

Patch/source checks are not behavioral or compilation checks. The historical report's executed results belong to its old revisions only.
