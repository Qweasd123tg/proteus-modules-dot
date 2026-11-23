# Skip portable mkdir calls for directories that already exist

The installed Linux portable launcher now checks its config directory
and each non-identical bundled directory target before invoking
`mkdir -p`. Missing, dangling or non-directory targets still use
the existing command. A path starting with `-` also uses it even if
the path exists, preserving GNU option parsing and errors. The `-ef`
same-directory guard, copy/update flags, settings upgrade and child
arguments are unchanged.

With the 17 tracked profile names and generated contents, the actual
wrapper used 5 → 5 mkdir launches on a clean fixture, 5 → 0 when all
directories existed, and 5 → 2 with two missing child directories.
The paired cases included regular relative paths, directory links,
same-inode links, non-directories, a dangling link and a leading-dash
relative path. File contents, modes, links, settings callback and
exit status matched. Both source tiers passed the proxy and shortcut
tests and shell syntax checks.

This comparison assumes stable ordinary directories and standard GNU
`mkdir`. It does not preserve side effects of a custom mkdir helper on
paths now skipped or promise equivalence during concurrent path edits.
Counts concern just mkdir launches, not startup time or memory.
No native client, real settings, install, release, or network ran.
