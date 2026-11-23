# Analysis: build the final ToolResult text directly

Trim the body before building the display string. A nonempty body retains
the newline after the colon; an empty or all-whitespace body does not. The
call ID, including any whitespace inside it, is left intact. The existing
truthy output-or-error choice and value conversion remain unchanged.

The formatter now concatenates the final string rather than formatting an
untrimmed string and copying a trimmed version. That removes the full
staging string, not the existing value conversion or later UI copies.

The one-file patch targets Extensions
`923077d3967ae7063a6556bc378c09f97abc2854`. Git and GNU patch
forward/reverse checks restored the exact stock bytes at zero fuzz.

## Verification

The exact candidate helper and source-lifted stock expression passed 6/6
paired byte tests in debug and optimized Rust 1.95.0, with no dependencies
beyond the standard library. The stock lift supplies the converted call
ID and output as typed Strings. Tests cover missing body, all Rust Unicode
whitespace, literal identifiers, preserved leading whitespace and NUL,
representative 2–32 KiB outputs, and a large trimmed suffix.

The value-selection source is byte-identical. The full Analysis crate,
JSON conversion, and UI were not run. No timing, allocator, or memory
benchmark was run.
