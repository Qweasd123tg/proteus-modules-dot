# Desktop: compare async paste targets without copying selections

When an asynchronous clipboard read completes, the editor checks that the document and ordered selections still match the original paste target. The old check built a second owned selection vector. The new check borrows the current selections and compares the revision, selection count and every selection in order. The original snapshot stays owned across the clipboard read, and the editability and focus checks are unchanged. The synchronous paste path is untouched.

The isolated Rust comparison passed 27 initial snapshot controls and 108 paired observations. With 4,096 selections the comparison went from one temporary allocation of 229,376 bytes to none, both for a match and for a stale revision. With one selection it went from one 56-byte allocation to none. The original snapshot stayed live in both variants, and neither variant retained comparison memory. Verdicts matched for altered selection fields, changes in selection order, and editability and focus controls. These are requested allocator bytes for the comparison, not measurements of the full editor, OS clipboard, or process memory or latency.

The patch applies and reverses directly on Proteus Desktop main at `4f8db605940c00d48b91cd32f35f8adbc7e7a339`. No prior patch is required for the owner hunk.
