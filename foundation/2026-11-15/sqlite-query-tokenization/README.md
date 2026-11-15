# SQLite query tokenization: delivery candidate

Source-only Rust proposal for the already reported C2 punctuation recall defect. This folder publishes evidence and a patch; it does not apply changes to Proteus upstream or deploy a fix.

Start with [REPORT.md](REPORT.md), the [patch](literal-fts-query.patch), and [independent review](SQLITE-QUERY-INDEPENDENT-REVIEW.md). Source provenance and text-application checks are included.

Python 3.12.14 / linked SQLite 3.53.1 matched 27/27 explicit-expression expectations. This is exploratory representation evidence, NOT execution of the Rust normalizer, bundled SQLite regression, or a compilation result. Six new Rust tests and one updated assertion are NOT RUN.

Benefit: SQLite owns tokenization on both index and query boundaries instead of a lossy second tokenizer. No exact punctuation identity or full Unicode equivalence guarantee. No speed/memory improvement measured. Before production adoption, run the actual library tests, format/build checks and appropriate export/process regression against the real lockfile.
