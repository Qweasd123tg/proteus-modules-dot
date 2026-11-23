# Markdown: pre-size the reference table and prose buffer

When a segment has reference definitions and contains an opening bracket, Markdown prepends the ordered definition table before passing it to the inline renderer. The old builder joins the table first and then grows its buffer to append the separator and prose. The new builder checks the complete byte length and reserves that capacity before writing. Definition order, duplicates, separators, prose, and the inline call are unchanged. When either guard fails, the original source is still borrowed directly.

Exact Extensions stock **923077d3** and the same source with #519 were verified. The Rust 1.95 debug and optimized checks pair the exact extracted prose functions and use the exact reference collector with a synthetic AST and an inert inline sink. They do not run the Markdown parser or the native extension package.

For a synthetic 32-reference table plus 8 KiB of prose, the stock table join has 2,175 bytes of capacity before appending, while the complete input is 10,369 bytes. The new buffer is sized for the complete input before writing. This shows the growth removed at this assembly site, not allocator traffic, latency, or process memory.
