# Desktop: share unchanged standalone tools with the archive window

One M391 patch. A rendered history archive often retains part of the live
tail. Before this change, the two transcripts shared assistant text but each
kept a complete copy of a standalone tool result, arguments, metadata and
terminal reference. The display row now moves each wire-owned standalone
tool into shared storage. A live Core or Codex event detaches only the tool
it edits. Saved rows keep their prior bytes; after the archive is dropped,
the next live event can edit the sole remaining owner in place.

Keep the **same logical row charge** as the old inline representation.
The existing row, byte and visible-page limits do not admit additional
history as a side effect of sharing. Existing page splices, stable keys,
capabilities, approval/terminal behavior, disclosure and tool hint data
are unchanged. The declarative plugin-facing projection is still the exact
owned public DTO; only the Desktop's internal ownership changes. Nested
subagent tool storage, source wire types, buffering, and SSE are untouched.

## Native differential verification

Exact M391 Desktop Transcript, History, row/stamp and pinned Core Contracts
compile in both arms. The typed saved baseline and pages pass through a
real serde_json roundtrip before the normal history reducer. All transcript
unit modules, plus native first-Older, cache pressure, real runtime
resolution/approval/terminal/finish, drop and Codex delta/replace controls
are compiled and run; 80 tests each on default and preserve-order JSON in
both arms. Core and Codex mutation controls verify that the archive stays
unchanged, only the edited tool detaches, and after closing the archive
an untouched former alias needs no large recopy. Clip and trim controls
keep 100 / 55 / 80 rows (below budget / beyond budget / mandatory anchor)
and match logical bytes and content digests.

The real chain iterator uses the same typed `&AppTranscriptTool` items,
and the plugin-facing bridge still clones the owned DTO. Both boundary
expressions are type-checked in the native wrapper. All direct `.tool`
source uses were inventoried; this is not a whole Desktop GPUI build,
HTTP benchmark, app latency or process RSS/PSS measurement.

| Native first Older acceptance, 50 saved + 50 retained live rows, 40 live tool results | Stock | Candidate |
| --- | ---: | ---: |
| Default JSON: net allocator-requested bytes outstanding | 3,055,461 | 661 |
| Preserve-order JSON: net allocator-requested bytes outstanding | 3,021,829 | 637 |
| Separate result owners avoided / archive & live shared references | 0 | 40 |

The net measure starts after the owned page exists and ends immediately
after the actual history acceptance. Common ownership transfers and drops
are included in both arms. Default mixed cold rows save 6,480 B in the
reset stage; all-tool cold rows with no possible archive sharing cost
1,200 B more per 50 rows and one small allocation per standalone tool.
A first mutation while an archive still owns the old payload may need
one copy at that point. These figures describe ownership, not a general
first-open speedup.

`composition.json` authenticates the canonical source through #632.
The patch is after the current #624 constructor layout and #628 child
link path. It commutes with the unrelated #632 raw HTTP-body reserve and
reverses exactly with the prior suffix.

With Rust 1.95 and the locally verified Core/Desktop registry closure:
`sha256sum -c SHA256SUMS`; `python3 verify.py --vendor PATH`.
Optional `--target-dir` reuses compiled registry artifacts, but stock and
candidate are built from separately rehydrated source and distinct
package names.
