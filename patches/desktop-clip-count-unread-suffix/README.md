# Count the unread suffix of clipped text

When a preview was clipped, Desktop's shared formatter counted lines again from the start. Continue from the same iterator instead. If the current line was rejected, it still counts as hidden. A clipped first line is still shown, so it does not.

Line and byte limits, UTF-8 cuts, line endings, whitespace and both truncation labels are unchanged. Tool and plain-code callers use their existing 400-line/40,000-byte caps. Approval previews still use 24 lines/6,000 bytes; the original action text is unchanged and remains available under the exact same truncation condition. Nothing changes how an approval is requested or acted on.

In the lifted formatter, a 128 KiB single-line fixture went from two logical line visits to one. A clipped 1,000-line tool fixture went from 1,401 to 1,000; a 40-line approval preview went from 65 to 40. The unread tail is still counted. These are formatter-level visits, not timing, physical byte traffic, or an app benchmark.

Rust 1.95 debug and optimized each passed 12 tests, covering 46,810 paired clip outputs and 396 paired approval display projections. Forward and reverse application restored exact bytes and mode. No GPUI/native app, real approval, clipboard, or server action ran.
