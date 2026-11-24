# Markdown: release a replaced prose segment before compiling its new source

Under unchanged renderer and reference policy, an ordinary content edit can
keep the same prose ordinal while changing its source. The old renderer kept
the mismatched segment's source and widget live until the whole document
returned. Remove the previous segment by its structural id before rebuilding.
Return it unchanged only on an exact source match; otherwise drop its owned
source and widgets before compiling the replacement. Prose ids are unique:
each belongs to an increasing fence ordinal or the final tail, and a retained
prefix resumes strictly after its last ordinal. Neighboring reusable segments,
the verified fenced prefix, invalidation guards, routes, render output, errors
and all limits are unchanged. This is the common same-policy streaming path,
not #634's renderer-policy or definition-scope change; no Node code changes.

**Base:** exact full 467-entry Extensions M395 source archive. All 467 local
M391 plus read-back #634 stock inputs independently match its bytes and modes.
Only `packages/markdown-render/src/render.rs` changes. Original Cargo.lock,
public APIs, protocol and dependencies remain untouched.

**Verified:** all 52 original unit and three native process tests in both
arms, plus the paired native allocation/reuse witness. Nine replies through
the real Markdown stdio process are byte-identical (6,147,543 bytes,
SHA256 `e5606f9283b03210914cd44294fb018bfd644f9b3373f9e06994563ed5187757`).
The script exercises ordinary large prose append, repeat, append after an
immutable fence, edit of the fence, new reference, provider toggle, Unicode,
CRLF and close/reopen in another scope.

The allocator scope wraps actual `Document::render` after a first render
populated its real cache, with 1,230,000 old prose payload bytes. Matched
native fixture outcomes:

| Case | Before incremental peak live bytes | After |
| --- | ---: | ---: |
| Edit single prose segment | 104,861,492 | 102,401,084 |
| Edit prose tail after retained fence | 104,862,116 | 102,401,704 |
| Repeated unchanged fenced document | 1,233,344 | 1,233,344 |
| Prose reused after nearby fence edit | 104,867,722 | 104,867,722 |

This releases about 2.46 MB of overlapping live source and widget allocations
early in each changed-prose case. Result bytes, gross allocation requests and
net bytes at return are unchanged; stable neighboring HTML and cached fence
payloads retain their pointers. The gauge tracks net requested Rust heap
layouts relative to the pre-existing document, not OS RSS/PSS, whole app
startup or runtime latency.

**Reproduce** with Rust/Cargo 1.95.0 x86_64 Linux and verified locked vendor:

    python3 proof.py --baseline /path/Extensions-M395-source.tar.gz       --vendor /path/vendor --work /path/scratch

Only source.patch is the product change. The proof compares exact old/new
tracked state, actual native outputs, allocator controls, and reverses all
467 files back to the input bytes and modes.
