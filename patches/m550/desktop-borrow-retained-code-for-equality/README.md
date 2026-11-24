# Compare retained code without copying it first

Borrow a contiguous editor buffer directly and use Ropey's byte comparison for multi-leaf text. The setter and its arguments are unchanged.

Apply `source.patch` to the exact Desktop source leaf identified in `receipt.json`. In a native test of an unchanged 2 MiB code block, peak requested bytes during the comparison fell from 6,291,504 to 256. The text and setter behavior matched across 23 cases. This measures the comparison path, not GPUI or whole-app memory.
