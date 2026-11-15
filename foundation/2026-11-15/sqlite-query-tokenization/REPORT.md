# SQLite recall: one tokenizer owns indexed and queried text

Status: **source-only Rust candidate for known C2, not a new finding or runtime-verified product fix**. A later bounded Python SQLite representation probe is recorded below; it does not execute the Rust candidate. No upstream source, branch, persistent database or executable was changed. No publication was performed by this worker.

## Baseline and deduplication

- Proteus Modules main: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Proteus Core main: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Actual Modules Core dependency: `41bdfffa6e70228278b4abc758b7f81a12672f35`, unchanged by the proposal. The MemoryItem/MemoryQuery source is identical at main and this pin.
- Delivery main: `048dfee679566d87869900de6e9153bba0dc51b3`, including PR120. PR85–120 titles and the delivery tree were checked for deduplication; see `DEDUP.json`.
- C2 was already reported with historical SQLite execution in [PR85 context-memory](https://github.com/Qweasd123tg/proteus-modules-dot/blob/048dfee679566d87869900de6e9153bba0dc51b3/research/proteus-continuous-audit-2026-11-13/evidence/context-memory/REPORT.md). `PRIOR-C2.md` is only the relevant excerpt. Those historical results do **not** validate this candidate or the fresh dependency pin.
- The separate memory typed-JSON cleanup HOLD is not reopened. PR118 delivery and PR120 concurrent-wait proposals are unrelated. No production source overlap with PR106–120; documentation composition and combined compilation have not been tested.

The initial bounded context-pack retrieval/admission read found no additional consequential finding worth publishing. The candidate below addresses the existing shared recall defect, rather than labeling a weak retrieval heuristic as a new bug.

## Existing failure and common owner

`context_provider/sqlite-memory/src/lib.rs:175–188` currently splits on whitespace, then deletes every character except alphanumeric, underscore and hyphen before quoting the remainder. Consequently `src/config.rs`, `Config::load`, and `v1.2.3` become `srcconfigrs`, `Configload`, and `v123`. The schema indexes the original content with FTS5's default tokenizer. The query transformation therefore invents a joined term that was not indexed from that text.

Both `MemoryTool` (`tools.rs`, recall branch) and `MemoryProvider` (`provider.rs`) call the same `SqliteMemoryStore::recall`, and `recall_impl` owns this expression. Automatic context memory retrieval delegates through that provider. Fixing the one existing expression boundary reaches both consumers without new APIs, helpers, storage formats, modules or framework.

## Proposed invariant and precise semantic change

For each whitespace-delimited span accepted by the existing eligibility predicate, pass a quoted literal phrase to the table's tokenizer instead of deleting its internal characters. Embedded quotes are doubled. NUL is explicitly mapped to a space inside the phrase. There are no changes to SQL statements, schema, store lifetime, database paths, metadata decoding or public DTOs.

The old condition “filtered string is nonempty” is exactly replaced by “any character satisfies the same alphanumeric/underscore/hyphen predicate.” Thus the old empty/recent gate is retained. Whitespace spans remain joined by `AND`. The `*` stays outside each quoted phrase. Underscore/hyphen compounds already had this phrase behavior and keep it.

Intended behavior changes: punctuation-separated words are no longer concatenated; e.g. the query literal is now `"src/config.rs"*`, not `"srcconfigrs"*`. The former erroneous joined-token matches may disappear and previously missed original terms may match. This is not a guarantee of byte-string/path identity, substring search, all-token-prefix matching, or unchanged result ordering. The ranking algorithm is unchanged, but changed query terms can change scores and ordering.

### Primary-source basis

[SQLite FTS5 strings, phrases and prefixes](https://sqlite.org/fts5.html#full_text_query_syntax) specify quote doubling, tokenizer-owned phrase extraction, and prefix matching only for the last token before an outside `*`. [The default tokenizer](https://sqlite.org/fts5.html#unicode61_tokenizer) supplies case/diacritic and separator behavior. The proposal uses that existing behavior rather than recreating it with Rust character splitting. The [SQLite parser source](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_expr.c) treats NUL inside a quoted string as an unterminated literal; NUL-to-space is an explicit separator policy, not literal-NUL support. These external sources were read, not executed; the parser link is current upstream source, not the bundled SQLite dependency's exact build.

## Proposed tests, NOT RUN

Six new tests in `src/tests/recall.rs` plus one updated existing expression assertion cover:

1. Exact developer-term queries versus misleading joined-token records: paths, `::`, versions, embedded quotes and `+`.
2. Ordered/adjacent phrase semantics and prefix only on the last token, with negative controls for expanded intermediate words and inserted path components.
3. Existing unordered whitespace-AND/prefix behavior and underscore/hyphen phrase behavior.
4. A combining-mark self-query left to SQLite instead of a second Rust tokenizer.
5. NUL-to-space, distinguishing a phrase match from the old merged term.
6. Existing empty/punctuation-only recent fallback and the distinct legacy `_`/`-` empty-token phrases.

Tests exercise the real in-memory store methods when eventually run, not a Python reimplementation. They have not been compiled or executed. No process-boundary, bundled-component or live-provider checks were performed. Existing zero-limit and metadata-error tests are unchanged.

## What was actually checked

- 16 source reads: 14 Modules files and the MemoryQuery contract at each of Core main/pin. Local bytes match their Git blob IDs; see `SOURCES.json` and `READ-VERIFICATION.json`.
- The patch applies to an isolated baseline copy with `git apply --check --whitespace=error`; applying it produces byte-identical `after/` files. `PATCH-VERIFICATION.json` records only these text/hash checks.
- Exact independent source review found no source-level blocker: `SQLITE-QUERY-INDEPENDENT-REVIEW.md`.
- No Rust toolchain, rustfmt, Cargo, project scripts, linked rusqlite/bundled SQLite, app, provider calls or Rust tests were run. A source review and a clean patch application are not compilation or test evidence.

### Later bounded Python SQLite representation probe

At the coordinator's request, `python_fts5_probe.py` was executed against Python
`3.12.14` and its linked SQLite `3.53.1` (`ENABLE_FTS5`). SQLite source ID:
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.

All **27 explicit-expression cases matched their stated expectations**. Results
and compile options are in `PYTHON-FTS5-RESULTS.json`. The probe creates only
in-memory tables using the existing content/kind FTS5 shape. It does not import
repository code and does not port or execute the Rust query normalizer: MATCH
strings are explicit fixtures.

Cases cover paths/namespaces/versions, embedded and doubled quotes, plus signs,
joined-token negative controls, phrase adjacency, final-token prefix versus an
inside-quote star, existing whitespace AND/compounds, combining-mark self-match,
and empty token controls. The raw quoted NUL control returned `unterminated
string`; the explicit NUL-to-space expression matched the two-word record, not
the merged term. `"-"*`, `"_"*`, `""*`, and `"!!!"*` matched no records. A direct
empty MATCH expression returned a syntax error; the separately selected recent
SQL branch returned newest records first. Thus retaining the existing branch
gate matters; the probe does not test Rust's selection of that gate.

This is representation evidence on the available Python engine, **not** a
Rust compile/test PASS, `rusqlite = 0.41.0` / `libsqlite3-sys = 0.39.1` bundled
regression, process-export check, or validation of all Unicode inputs. No
candidate code change was needed from these observations.

The production function grows by five lines including explanatory comments. The benefit is semantic ownership: remove a lossy independent token transformation, not claim a LOC reduction or measured latency/RSS improvement. The implementation does allocate escaped literal strings; no performance improvement is claimed.

## Remaining limits and next gate

- The retained eligibility predicate is not a complete Unicode61 tokenizer. Spans containing only characters the old predicate rejected remain skipped, including private-use-only text. No arbitrary-Unicode or custom-tokenizer equivalence is promised.
- Whitespace still separates AND terms, even when input contains quotes. User-supplied quote syntax is literal, not a phrase-query language.
- Prefix applies only to the last tokenizer token in each span. Punctuation identity is deliberately not preserved by token search.
- NUL-to-space is a specified normalization; arbitrary embedded-NUL corpus behavior was not exercised.
- Query/rank and result-limit policy are unchanged; whole-task AND retrieval quality, memory admission budgets and database consistency are outside this candidate.
- Required before calling it tested: run the affected `sqlite-memory` library target against the actual lock/pin, format-check the final source, and run the appropriate process/export scope before deployment. Do not replace this with historical C2 logs or publication status.

Patch SHA256: `333558ca5742e39adeeb10347c8382dce78c0ff14cbe6b3e455cd48b9bd00a95`.
