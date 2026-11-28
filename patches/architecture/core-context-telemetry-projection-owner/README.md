# Separate context telemetry projection from log reading

Make the event projector and its result available directly to both the log
reader and the cache. Only the reader still chooses the session, handles file
errors and validates source stamps. The projector continues folding matching
events in file order and retains the same usage, diagnostic and redaction
behavior.

Use source.patch on the pinned Core revision or source-after-stack.patch on
the cumulative tree. Five focused native checks per base, including a
synthetic log whose invalid UTF-8 must fail with the original file context.
