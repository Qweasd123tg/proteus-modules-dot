# Borrow paths when encoding a storage locator

Serialize the identical ordered locator fields using borrowed Path
values; parsing still produces the original owned paths and performs
the same checks. Move the locator into a newly reserved descriptor,
preserving fallible serialization before the existing-target branch.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. On both optimized standalone
libraries, the typed Rust allocator probe observed three fewer fresh
requests (643 requested bytes) for Create of a new reservation, two
(290 bytes) for Open by directory or file and for writer-backed
OpenSnapshot, and no change for Describe of a reservation. Realloc
traffic was equal in these fixtures. 117 tests (one ignored) per arm.
Raw locator JSON (including escaping and optional fields), Unix invalid
Unicode errors and owned parse agree with the old serializer.

Use source.patch for the exact base, or the verified after_888 rebased
selector from receipt.json for that pre-tree; do not stack selectors.
No combined build, elapsed time, RAM, or installed runtime claim.
