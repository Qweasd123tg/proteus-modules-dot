# Pi compaction: reuse the projected history array for entries

Only after projecting the complete history and passing the existing token and compaction checks, fill the private projection array with the existing entry wrappers. Entry IDs, parent links, retained summaries, payload objects and failure paths remain unchanged.

The exact local Pi hook passed 21 controls across the current and scoped versions with inert upstream dependencies. In the successful synthetic 6,144-message case, the original mapped two full history arrays; the updated hook passed the original array to preparation instead. Results matched, including with a supplied estimate. Rejected compaction still maps one history array and does not prepare entries.

The receipt identifies the owner/pin and scoped bases. This is an array-object check, not a test of the installed Pi SDK, application timing or RAM.
