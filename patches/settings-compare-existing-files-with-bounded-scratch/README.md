# Bound the existing-settings comparison buffer

Compare each existing file with the desired bytes using one reusable
64 KiB scratch buffer. The comparison still opens the same paths in
the same order and reads through EOF even after detecting a difference.
A later read or close error still aborts the batch before path checks or
writes. Missing files, symlink checks, backup, atomic replacement and
rollback keep their existing paths.

On stock and Desktop + #485/#493, three actual 16 MiB fixtures (equal,
first-byte difference, last-byte difference) each read all 16 MiB.
Stock returned one full-size byte string from the comparison read;
the candidate used one 64 KiB scratch buffer. Thirteen synthetic cases
per tier also covered short/long data, chunk boundaries, open/read/close
failures, links, a normal write, and rollback after an injected replace
error. Existing settings migration and shortcut tests passed.

The change bounds comparison scratch, not total migration memory or
bytes read. Small existing files can need more scratch than before;
chunked equality can also cost extra CPU. No faster I/O, elapsed time,
or native RSS improvement is claimed. Fixtures used no real settings,
native app, installation or network.
