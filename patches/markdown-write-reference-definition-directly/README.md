# Markdown: write reference definitions into one buffer

Write the identifier, destination, and optional title directly into the
final definition string. Do not build separate escaped destination
or title strings, or a formatted title wrapper. The eight escape
replacements, delimiters, and absent-versus-empty title behavior are
identical. Definition traversal, end offsets, and the Markdown parser
and link policies are unchanged.

The one-file patch targets Extensions
`923077d3967ae7063a6556bc378c09f97abc2854`. Exact Git and GNU
forward/reverse application restored the stock bytes at zero fuzz.

## Verification

Rust 1.95.0 built the complete stock and candidate source files into a
standard-library-only test, once in debug and once optimized. Both passed
6/6. The test uses an inert typed stand-in for the Markdown AST. It checks
exact bytes and ordered end offsets, all current escapes, missing and
empty titles, escaped-looking and Unicode text, missing-position
exclusion, 32 reference definitions plus long and dense controls.

This verifies the changed writer and collector under typed inputs. It is
not a Markdown parser, Cargo package, or installed Desktop test. One output
buffer does not guarantee one heap allocation, lower retained capacity,
or a speedup. No timing or memory benchmark was run.
