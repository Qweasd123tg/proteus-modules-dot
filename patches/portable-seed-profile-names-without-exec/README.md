# Avoid external basename for ordinary portable profile entries

Scope: the installed Linux Portable Desktop launcher at
`f8cc40177ad3ab3d8ec36447a899332778f03268`. Extract the filename of each
entry in the portable `share/configs` glob with shell expansion rather
than the external utility. For a trailing LF, keep the original
`basename` substitution so it still strips every trailing LF, including
the utility's own newline. Copying, symlink checks, existing profiles,
storage upgrade, proxy hand-off, arguments and exit codes are unchanged
under standard utility semantics.

The pinned Core roster has 17 visible top-level entries (13 files and
4 directories). With those names and generated contents, the actual
wrapper issued 17 → 0 `basename` launches on both a partially seeded and
a populated fixture. Profile trees, source files, arguments, upgrade
calls and status matched. An executable witness counted each invocation
and delegated unchanged to GNU `basename`. Edge fixtures cover interior
and trailing newlines, spaces, a leading dash, hidden and unmatched
entries, a literal star, symlinks, pre-existing files and a renamed
portable directory. Existing proxy and shortcut tests passed on both
versions.

An ordinary name no longer uses a custom basename override or requires
that external executable. The legacy LF case still does. No native
client, real profile, live provider, install or network ran. Counts refer
only to this utility, not overall subprocesses, elapsed time or memory.
