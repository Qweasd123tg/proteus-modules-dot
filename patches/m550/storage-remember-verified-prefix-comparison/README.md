# Remember one verified historical snapshot comparison

A repeat of the same successful historical comparison can use the prior
prefix revision and digest on the same live snapshot only after the
backend reauthenticates the pinned source. Inline JSONL still hashes
all its pinned bytes; external JSONL still uses the original full
replay. Failed reauthentication takes the original error-producing
path. SQLite relies on the same pinned read transaction. This does not
mark the full snapshot semantically verified.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. In the typed three-record fixture,
same-handle repeats dropped 6→0 decodes for inline JSONL and 3→0 for
SQLite. First and fresh-handle cases were unchanged; external JSONL
remained at six decodes. A changed journal suffix and missing/corrupt
external chunks still fail. Both arms passed 117 tests (one ignored)
and built optimized standalone libraries. No app timing or PSS claim.
See receipt for verified source composition with #878 and other drafts.
