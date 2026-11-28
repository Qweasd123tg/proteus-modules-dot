# Separate shared host-call operations from local compaction

Move four existing helper bodies, unchanged, into a private `host_call` module
within `codex-context-preparation`. Remote compaction and generic input
estimation no longer import their shared operations from the local summary
and recovery modules. Local and remote retry policies and request composition
remain distinct.

- `source.patch`: strict patch for Modules `b476a8cca8f0906455753014622d8fbdc08e7899`.
- `source-after-stack.patch`: strict variant for the cumulative Modules tree recorded in the receipt.

Both variants were compiled offline and verified with nine exact native
in-process fixtures. No actual provider or tool was invoked.
