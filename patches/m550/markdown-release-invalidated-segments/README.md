# Markdown: release invalidated render segments before rebuilding

The renderer previously kept old widgets and their source until return even
when the next render was already barred from reusing them. Changing renderer
registrations now releases those dead segments before parsing; changing
reference definitions releases the non-reusable suffix after moving any
verified prefix to the new document. The existing full-reference-scope and
prefix/closing-line checks stay in place. Prose whose source and policy
still permit reuse is not dropped. With invalidated nodes removed from the
reuse pool, the per-segment reuse-disable argument is unnecessary.

**Base:** exact M391 full 467-entry Extensions tree, including published
#630. Local M387+read-back #630 input bytes, modes and links all match the
independently materialized full archive. Single product path
`packages/markdown-render/src/render.rs`, no protocol, lock, dependencies,
validation rules, parser or display limits changed.

**Native verification:** 52 existing unit and three integration/process
tests in each arm. The actual Markdown stdio binary gives nine byte-identical
replies (3,027,035 bytes, SHA256
`fe7a0aad16deeabead780a24582d83d0d310aef25d1df552324cc9beee0c883d`),
including streaming across a newly defined late reference, a renderer
registration toggle, UTF-8/CRLF/NUL, nested/open/literal fences and reopen.

A separate paired allocator scope is actual `Document::render` directly
after an authentic rendering step that populated its retained cache. Both
the old and new rendered text and reused buffer identities are checked.

| Fixture, peak rise in net live requested bytes during next render | Before | After |
|---|---:|---:|
| Registration policy changed, 1,292,000-byte code body | 5,172,655 | 3,878,874 |
| New late reference, retained prefix and 782,036-byte prose suffix | 84,694,790 | 83,903,884 |
| Fence edited under unchanged policy and refs, reusable adjacent HTML | 16,897 | 16,897 |

Cumulative requested allocations and net bytes at function return are
unchanged for these cases. This is the measured rise relative to the same
pre-existing Document within one thread, not RSS/PSS, overall app peak,
GUI startup, or measured latency. The bytes are live requested allocator
layouts at operation boundaries, not OS page accounting.

**Reproduce:** Rust/Cargo 1.95.0 x86_64 Linux and verified locked local vendor:

    python3 proof.py --baseline /path/Extensions-M391-source.tar.gz       --vendor /path/vendor --work /path/scratch

The proof checks exact old/new source bytes, actual native routes and
allocator controls, the original lock and reverse of all 467 tracked files.
Only source.patch is the production change.
