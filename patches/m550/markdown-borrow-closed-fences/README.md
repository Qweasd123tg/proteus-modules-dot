# Markdown: borrow closed fence bytes until an owned widget is needed

Fenced code still needs the exact original bytes: the parser's code value can
normalize whitespace, line endings and NUL. Instead of cloning the original
range while producing each parsed closed block, keep a borrow into the render
input and materialize it only when constructing its owned widget. This lets
the parser's temporary code body drop without a raw-source copy being live at
the parse→render boundary. An open or indented block still transfers the owned
parser value, and incomplete math still stays in prose. The widget keeps the
same independent ownership and old tight-capacity policy; no lifetime escapes
the call. Fences, nested blocks, routing, language aliases, output, validation
and all limits remain unchanged.

**Base:** exact M380 Extensions native Cargo archive with 151 inputs, including
#620. Locally composed M376 + the published #620 matches every archived stock
input before the change (bytes/modes and license symlinks). Two paths,
`packages/markdown-render/src/{fences,render}.rs`, one coherent ownership
change. The render path retains #607's reference handling and does not modify
it. No lock/manifest or dependency changes.

**Native proof:** both arms passed 52+3 original package tests and a separate
allocator witness. The real Markdown stdio process returned nine byte-identical
protocol-v4 frames, 3,027,035 bytes, SHA-256
`fe7a0aad16deeabead780a24582d83d0d310aef25d1df552324cc9beee0c883d`. The cases
cover embedded/literal and claimed descendants, a large Unicode/CRLF/NUL
fenced body, streamed edits with newly resolved references, provider toggles,
open and malformed closers, math alias fallback, nested fences, and reopen
after closing. The proof compares the widget messages; it does not measure a
Desktop/GUI session or downstream diagram rendering.

The calling-thread allocator meter around the **actual fence parse** for two
large closed blocks and one small open block removes exactly two requests,
9,555,555 → 7,971,552 cumulative requested bytes, and 1,584,593 → 590 net
live bytes at parse return. Both closed pointers now match the original input
slices; the open one remains parser-owned with its original normalized body.
The observed peak inside the parser is unchanged at 4,183,215 net live bytes,
and the downstream widget still requires owned bytes. These scoped allocator
observations are not PSS/RSS, top-level peak, or latency improvements.

**Reproduce** with Rust/Cargo 1.95.0 x86_64 Linux and verified locked Cargo vendor:

    python3 proof.py --baseline /path/Extensions-M380-native-inputs.tar.gz       --vendor /path/vendor --work /path/scratch

Only source.patch is the product change; the proof checks the exact whole-input
forward and reverse state, original Cargo.lock, both native proto routes and
the scoped allocator measurement.
