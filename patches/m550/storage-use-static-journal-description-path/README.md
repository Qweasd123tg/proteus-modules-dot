# Select the journal filename without constructing a backend

Metadata only needs the journal path. The same file-name constants and
Path::join operation now work directly on the backend kind; real replay,
write and recovery still instantiate their existing backends.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. On both optimized standalone
libraries, a Rust allocator probe through the typed service observed
two fewer fresh requests in creation and ordinary Open (by directory
or journal file), one in Describe of a reserved session, and five in
a writer-backed snapshot. Result paths, revision, and the opposite-format
error stayed the same. The probe does not claim fewer reallocations,
RAM, filesystem operations, or elapsed time. Both exact arms passed 116
tests (one ignored).

Five same-file prior draft pairs apply and reverse on exact rebased
source; use only a selector for its exact pre-tree. Not a combined build.
