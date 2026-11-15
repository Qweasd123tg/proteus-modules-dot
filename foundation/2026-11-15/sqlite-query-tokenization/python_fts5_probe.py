"""Bounded representational probe, NOT execution of the Rust candidate.

All MATCH strings are explicit fixtures. No Python port of Rust normalization.
Only an in-memory database is used; generated evidence is written beside this file.
"""
import json
import platform
import sqlite3
from pathlib import Path


def database(contents):
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
CREATE TABLE memory_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 kind TEXT NOT NULL,
 content TEXT NOT NULL,
 metadata TEXT NOT NULL DEFAULT '{}',
 created_at INTEGER NOT NULL
);
CREATE VIRTUAL TABLE memory_fts USING fts5(
 content, kind, content='memory_items', content_rowid='id'
);
CREATE TRIGGER memory_items_ai AFTER INSERT ON memory_items BEGIN
 INSERT INTO memory_fts(rowid, content, kind)
 VALUES (new.id, new.content, new.kind);
END;
""")
    conn.executemany(
        "INSERT INTO memory_items(kind, content, metadata, created_at) VALUES ('fact', ?, 'null', 0)",
        [(text,) for text in contents],
    )
    return conn


results = []


def check(name, contents, expression, expected=None, expected_error=None, recent=False):
    with database(contents) as conn:
        error = None
        actual = None
        try:
            if recent:
                rows = conn.execute(
                    "SELECT content FROM memory_items ORDER BY id DESC LIMIT ?1", (20,)
                )
            else:
                rows = conn.execute(
                    "SELECT memory_items.content FROM memory_items "
                    "JOIN memory_fts ON memory_items.id = memory_fts.rowid "
                    "WHERE memory_fts MATCH ?1 ORDER BY rank LIMIT ?2",
                    (expression, 20),
                )
            actual = [row[0] for row in rows]
        except sqlite3.Error as exc:
            error = str(exc)
        passed = (
            error is not None and expected_error in error
            if expected_error is not None
            else error is None and (actual == expected if recent else sorted(actual) == sorted(expected))
        )
        results.append(dict(
            name=name, contents=contents, expression=expression,
            mode="explicit recent branch" if recent else "bound MATCH expression",
            expected=expected, expected_error=expected_error,
            actual=actual, error=error, passed=passed,
        ))


for name, literal, joined, expression, old_expression in [
    ("path", "src/config.rs", "srcconfigrs", '"src/config.rs"*', '"srcconfigrs"*'),
    ("namespace", "Config::load", "Configload", '"Config::load"*', '"Configload"*'),
    ("version", "v1.2.3", "v123", '"v1.2.3"*', '"v123"*'),
    ("quote", 'alpha"beta', "alphabeta", '"alpha""beta"*', '"alphabeta"*'),
    ("plus", "alpha+beta", "alphabeta", '"alpha+beta"*', '"alphabeta"*'),
]:
    check(name + " literal phrase", [literal, joined], expression, [literal])
    check(name + " old concatenated control", [literal, joined], old_expression, [joined])

check("last token prefix and adjacency", [
    "src/config.rs", "src/config.rst", "src/configuration.rs", "src/extra/config.rs",
], '"src/config.r"*', ["src/config.rs", "src/config.rst"])
check("inside-star is not prefix control", ["src/config.rs"], '"src/config.r*"', [])
check("unordered whitespace AND and prefix", ["dark mode"], '"mod"* AND "dark"*', ["dark mode"])
for literal, expression in [("some_name", '"some_name"*'), ("some-name", '"some-name"*')]:
    check("existing compound " + literal, [literal, "some other name"], expression, [literal])

combining = "co\u0301de"
check("combining mark self-match", [combining], '"co\u0301de"*', [combining])
check("normalized NUL separator expression", ["alpha beta", "alphabeta"], '"alpha beta"*', ["alpha beta"])
check("raw NUL quoted parser control", ["alpha beta", "alphabeta"], '"alpha\0beta"*', expected_error="unterminated string")
check("doubled quote literal", ['alpha""beta', "alphabeta"], '"alpha""""beta"*', ['alpha""beta'])
check("trailing punctuation", ["React Router v6"], '"React"* AND "Router!!!"* AND "v6"*', ["React Router v6"])

for name, expression in [("hyphen", '"-"*'), ("underscore", '"_"*'), ("empty", '""*'), ("punctuation", '"!!!"*')]:
    check(name + " empty token phrase", ["first", "second"], expression, [])
check("empty phrase AND nonempty term", ["first", "second"], '"first"* AND "-"*', [])
check("explicit empty-expression recent branch", ["first", "second"], "", ["second", "first"], recent=True)
check("direct empty MATCH is not recent branch", ["first", "second"], "", expected_error="syntax error")

with sqlite3.connect(":memory:") as conn:
    version = dict(
        python=platform.python_version(),
        sqlite3_sqlite_version=sqlite3.sqlite_version,
        sqlite_source_id=conn.execute("SELECT sqlite_source_id()").fetchone()[0],
        compile_options=[row[0] for row in conn.execute("PRAGMA compile_options")],
    )
evidence = dict(
    scope="Python sqlite3 linked engine, explicit FTS5 fixture expressions only; not Rust/rusqlite/bundled regression",
    version=version, case_count=len(results), all_passed=all(x["passed"] for x in results), cases=results,
)
out = Path(__file__).with_name("PYTHON-FTS5-RESULTS.json")
out.write_text(json.dumps(evidence, ensure_ascii=True, indent=2) + "\n")
print(json.dumps({"version": version, "cases": len(results), "all_passed": evidence["all_passed"], "evidence": out.name}, indent=2))
for result in results:
    if not result["passed"]:
        print("MISMATCH", json.dumps(result, ensure_ascii=True))
raise SystemExit(0 if evidence["all_passed"] else 1)
