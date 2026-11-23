# Bound the input to the short tool preview

A long line could make `peek_block` search the entire input for a newline before cutting it to the visible byte budget. Give the existing preview formatter a UTF-8-safe prefix instead: its byte budget, one extra byte per potential CRLF line, and four bytes of lookahead. The formatter still makes the same line, UTF-8 and trailing-whitespace decisions.

The production 12-line, 2,000-byte preview now offers at most 2,016 bytes to its line iterator. In the paired fixtures, a 128 KiB first line went from 131,072 to 2,016 offered bytes. A giant line after eleven CRLF rows went from 131,127 to 2,015. Both previews remained exactly 2,000 bytes. This does not bound the entire tool row: its hidden-line count and optional full clip still use the original text.

Rust 1.95 debug and optimized each passed 14 tests across four arms: stock and after #542, both before and after this patch. Paired UTF-8 and boundary cases, tool labels, full clips, and inert approval display were byte-identical. The same patch applied and reversed to exact bytes and mode on both bases.

Offered input length is a formatter-level measure, not measured CPU time, physical memory traffic, RSS, or native app performance. No real approval or native app ran.
