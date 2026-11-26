# Core: borrow the context when a workflow emits an event

The worker workflow's event callback now borrows the existing Core context instead of cloning it. The same emitter handles the event, attribution, sequence, cancellation and errors. This avoids one full context copy at this callback only; it does not affect how other events are emitted or roll back an append that already started.

Both exact variants passed 77 focused native tests each, with 76 common control cases per build. The new gated-sink test covers success, sink failure and cancellation. Existing tests include the selected reference Codex process with synthetic fixtures, not the installed standalone Coding Workflow worker or all event producers. No timing or memory measurement was made.

Choose one version. On the exact Core owner, use `source.patch`. If you apply exact #811 first, use only the embedded base64 `alternate_scoped_patch` in `receipt.json`; check its SHA-256 before applying. The two variants are not additive.
