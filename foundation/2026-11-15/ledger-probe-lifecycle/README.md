# Ledger F2: instrumentation before solution import

Publication of a reviewed **proposal**, not an upstream deployment or a new finding. See [REPORT.md](REPORT.md) and the unchanged [patch](ledger-probe-lifecycle.patch).

Known benchmark-design F2 is addressed by one common import-lifecycle invariant: instrument documented OS functions before importing the solution in a fresh child interpreter. This removes reliance on solution import style or private module layout.

## Verified scope

Python 3.12.14 synthetic controls: baseline 2 qualified positives and 2 expected direct-import failures; candidate 8 successes and 10 expected rejections, including explicit `-O`. All **22 controls matched expectations**, not 22 pytest passes. Independent source, harness and recorded runtime reviews are included. Publisher reverified all recorded evidence hashes, 11 Git source blob identities, whitespace-strict patch applicability and applied bytes.

## Open gates and cost

No real Ledger, full pytest/public suite, gold refactors, historical regrade or benchmark run. Parent pytest wrapper integration, actual packaging and Python 3.13.9 remain unqualified. The candidate adds **63 Python lines and two interpreter starts**; no performance improvement is claimed. Python audit guards are not OS isolation.

Review documents retain their chronology: later final-revision sections supersede earlier source-only qualifications. REPORT.md records the completed synthetic stage. Private raw logs, runner, fixture workspaces and full source snapshots are deliberately excluded. Their hashes in reports identify reviewed private evidence, not downloadable attachments. SOURCE-CHECKS.json references private runtime evidence. Public artifact identities are recorded in PUBLICATION-SHA256.json.

This package changes only the delivery repository. Upstream sources and historical scores are unchanged.
