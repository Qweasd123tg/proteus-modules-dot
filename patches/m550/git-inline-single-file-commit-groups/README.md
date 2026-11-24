# Git commit inspector: avoid allocating a vector for each one-file group

Store a borrowed file inline while a path group has one member. A second member
promotes the group to the same four-pointer starting Vec used by stock. Group
and duplicate ordering, recursion, collapsed folders, file status and selection
are unchanged. One production leaf; no new dependencies or stored state.

The isolated native projection gate passed 10 fixtures and compared 60 complete
ordered JSON arrays. For both a flat and a grouped 128-file fixture, it avoided
128 allocator requests and 4,096 bytes of gross requested allocation. The
768-file stress fixture avoided 768 requests and 24,576 gross requested bytes.
Requested peak fell by 32 bytes on each of those three fixtures; retained bytes
were equal in all cases. Neither application memory nor latency was measured.

R1 remains HOLD at static preregistration, without a compiler or ELF. A separately
sealed proof-only R2 used the same product patch and Rust proof; its guarded build
and gate passed. Independently checked exact forward/inverse compatibility on
owner Extensions main and the actual Desktop extension pin; no prerequisites.
