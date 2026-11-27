# Borrow complete buffered JSONL records during archive scanning

Deserialize complete lines directly from the reader. Lines crossing a
buffer boundary still use the bounded fallback; the byte limit and
mandatory newline are unchanged. The writer lease, payload validation,
and archive rewrite rules are unchanged.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`; full-index apply and reverse verified.
Two optimized libraries built. For each arm 117
component tests passed and one was ignored. In an owned archive fixture
of 129 inline rows including one long row, fallback scratch copied
129→11 rows and 118805→37568 bytes. The journal bytes remained
identical, and malformed or unterminated suffixes retained their errors.
This is a copy counter, not elapsed time, physical I/O or process memory.
