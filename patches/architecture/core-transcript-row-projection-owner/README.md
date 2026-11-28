# Separate transcript row projection from the journal facade

Use the same row projection for in-memory messages and journal replay.
The journal imports the projection directly instead of reaching back through
the facade that exports the journal. Preserve journal scanning, row order,
retained attachments, tool-card distinctions and public entry points.

Use source.patch on the pinned Core revision, or source-after-stack.patch on
the cumulative tree. Verification uses focused native synthetic fixtures.
