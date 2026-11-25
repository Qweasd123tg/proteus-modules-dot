# Modules: avoid materializing all Cargo output lines at once

Standalone patch for `package.py` on Modules main `e8e77e306092344c00833f3456acba950c851fe3`, the Desktop-pinned Modules source, and the same source in M478.

Read already captured Cargo output in one batch at a time. A batch ends at a newline in the next 64 Ki characters, so ordinary logs spend less time holding a second copy of the output. If no boundary is found, use the old split on the remainder. Keep Python's exact line-separator behavior, diagnostics, artifact selection, package indexing, and full output attached to errors.

- Exact forward/reverse application. All 15 existing package tests passed on both arms with simulated Cargo.
- 3,177 splitter parity cases and 17 matched build-result controls, including Unicode boundaries, CRLF, undelimited text, diagnostic order, and failure output.
- With a prebuilt synthetic log of 2,328,211 characters, peak Python allocations inside the processing test fell from about 2.79 MiB to 148 KiB. This excludes the already captured log and measures neither Cargo nor application process memory. The tested timing does not establish a speedup.
