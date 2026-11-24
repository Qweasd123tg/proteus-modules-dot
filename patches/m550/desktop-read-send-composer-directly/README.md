# Desktop: read the composer text directly when sending

Ordinary Core-backed Send now copies a contiguous editor slice directly and uses an exact-sized conversion when the text spans multiple Rope chunks. The sent text is still trimmed, and the full original text is preserved for restoring a failed send. Empty drafts no longer build a temporary Rope cursor.

In the scoped native check, 22 cases, 220 allocation ledgers and 20 lifecycle recorder controls matched. Empty snapshot preparation went from 128 to 0 bytes; a contiguous 512-byte snapshot went from four allocation requests to one. For 2 MiB of untrimmed text, raw snapshot peak was 4,194,320 → 2,097,408 bytes, but peak for preparing both owned strings remained essentially unchanged. This is not an app-memory or end-to-end send benchmark.

The exact source hunk applies and reverses on the independently verified owner revision with no prerequisite. Full-file differences outside the hunk are preserved.
