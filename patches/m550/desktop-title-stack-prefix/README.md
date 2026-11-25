# Desktop: bound the allocation for a saved session title

Renaming a session used to gather all input words and join them into a full
temporary string before saving only the first 120 Unicode scalars. The new
collector retains the same whitespace and separator rules, encodes only the
saved prefix into a 480-byte stack buffer and copies the written bytes into
the saved string. Blank titles still clear the custom title without changing
pin or archive status. Proteus and Codex session keys are unchanged.

In the detached Rust proof, a one-character title went from 7 to 5 allocation
requests, and the 13-byte “Release notes” fixture from 8 to 5 (791 to 703
gross requested bytes). The synthetic two-MiB many-word fixture went from
25 to 5 requests and 35,652,329 to 810 gross requested bytes. With a
two-MiB token after one short word, requests went from 7 to 5 and logical
peak requested bytes from 2,097,952 to 798. All 10,355 semantic cases and all
16 allocation fixtures passed, including blank, Unicode and scalar-boundary
controls. Five short-title controls met the same preregistered timing guard.

The meter includes the map and key work but excludes the already-live input.
Splitting can still scan an entire long token or whitespace run. These
figures do not measure widget behavior, preferences I/O, process RAM or
end-to-end performance. The single hunk applies and reverses directly on
Desktop main without the rejected earlier variant.
