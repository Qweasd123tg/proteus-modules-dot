# Mermaid worker: check for non-whitespace without trimming source

The Mermaid worker used the trimmed string only to determine whether the input was blank. It always passed the original string to the renderer. Completed Markdown fences preserve their trailing newline, so trimming often yields a different string that is immediately discarded.

Use a non-stateful non-whitespace predicate instead. Keep the original input, error ordering, UTF-8 byte limit, rendering and response handling unchanged. The renderer still sees the original string, including whitespace.

Paired Node checks drive the pinned worker and renderer with owned inputs and compare complete responses. This removes the unnecessary trimmed value at the JavaScript level; it does not establish physical allocations, latency, or application memory savings.

Apply `source.patch` only to the exact Extensions owner in `receipt.json`. No alternate is required.
