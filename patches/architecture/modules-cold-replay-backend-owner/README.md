# Let the storage backend own cold snapshot replay

Move backend selection and the existing cold replay dispatch out of the
snapshot service. Keep the public BackendKind import, engine-specific
format and exact validation, ordering and publication behavior.

Use source.patch for pinned Modules and source-after-stack.patch for the
cumulative tree. Five native local tests per base include a fresh service
opening absent-cache history on both engines. No storage worker ran.
