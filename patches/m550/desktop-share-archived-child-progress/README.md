# M398 Desktop: retain the same frozen child progress in the archive

A live child-progress row owns up to 64 nested tool records. The earlier
standalone-tool ownership patch (#637) does not cover this type. When the
first Older page retains the live tail, cloning its child rows previously
deep-copied nested tool results, metadata, arguments and terminal references.
This patch shares each complete child-progress payload between views. A
live event detaches only the matching child before editing. A missing call
or rejected 65th tool does not trigger a detachment.

The logical history charge uses the same previous inline representation.
The visible anchors, original older-page limit, duplicate tool selection
(last row and last nested occurrence), cap behavior, child identity,
snapshot and renderer bytes, and extension-owned public DTO are unchanged.
This applies to active progress overlays, not the standalone-tool case
already counted. Persisted pages with no child-progress rows do not exhibit
the measured gain. A real first edit while both views retain a child can
still need a copy of that one whole child. After the archive drops, the
remaining owner's edit does not copy the payload.

## Native differential

Exact M398 Transcript, History, ContextSeek, stamp and native pinned
Contracts build for both arms. Real typed runtime events construct and
populate 48 + 64 nested tool results, and the actual history reducer
accepts a typed 50-row page against 50 resident live rows. The extension
adapter still produces the owned public child DTO. Both layouts pass all
80 tests per arm, including duplicate selection, missing and capped calls,
real session binding/approval/resolution/terminal/finish, changed nested
wire metadata, and release of the archive. Pressure tests preserve the
exact same 99-row trim and mandatory 100-row visible window even above the
8 MiB logical budget.

| First Older, runtime-generated child-heavy fixture | Stock | Candidate |
| --- | ---: | ---: |
| Default JSON: net allocator-requested bytes outstanding | 6,184,751 | 659 |
| Preserve-order JSON: net allocator-requested bytes outstanding | 6,126,039 | 571 |
| Independent child tool vectors still shared between both windows | 0 | 2 |

The owned input page exists before the meter starts. The endpoint is the
existing native model acceptance; common consumed owners/drops count in both
arms. The 100 rows, their exact logical charge, keys and typed digest are
unchanged. The test is not a complete Desktop executable, product HTTP/GUI
test, first-frame latency, or process RSS/PSS. No GPUs, Node, or settings
changed.

See `composition.json` for exact forward/inverse replay, after #637 and
commuting with the unrelated #639 font selector. With Rust 1.95 and the
verified Core/Desktop registry closure: `sha256sum -c SHA256SUMS` then
`python3 verify.py --vendor PATH`. Optional `--target-dir` reuses registry
build outputs; source is separately rehydrated for each arm.
