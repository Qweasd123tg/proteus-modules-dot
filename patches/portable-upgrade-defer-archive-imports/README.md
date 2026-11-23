# Defer settings archive imports until export or restore

The installed portable launcher invokes `upgrade-storage` when run
without arguments and without `PROTEUS_CONFIG_PATH`. That command
does not open an archive. Keep the archive-only imports in the archive
helpers, and add `TarError` only for archive CLI operations. Upgrade,
export and restore still use the same profile, credential, path, archive
and atomic-write checks. Direct archive helper calls still work.

On CPython 3.12.14, a disposable actual launcher run took the same
settings path and loaded 111 → 102 module entries in the settings helper.
This was true for an already selected profile, a legacy profile that
needed updating, and a rejected upgrade. `io` was already present; a
real archive command still loaded the archive dependencies. The counts
do not establish native startup time or memory savings.

Stock and Desktop + #485/#490 both passed the existing settings and
shortcut tests and 13 paired synthetic controls. The controls compare
archive members, profile bytes and mode, backup and restore results,
exit status and errors (including corrupt gzip and injected tar write
failure). No real settings, native client, build, install or release ran.
