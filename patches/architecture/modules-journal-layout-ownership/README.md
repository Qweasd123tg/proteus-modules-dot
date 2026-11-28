# Modules: define canonical journal names at the storage backend boundary

The JSONL and SQLite backends use the same two canonical journal names without one importing the other's codec just to identify a foreign journal. Archive, catalog, and session opening use the same names. The on-disk layout and format-selection rules are unchanged.

The regression uses literal names, opens either session directory or journal file with the intended backend, rejects both entry points with the opposite backend, and confirms that the original journal stays byte-identical.

Apply `source.patch` to Proteus-harness/Proteus-modules at `7274147162cb226f05df13a52b4a271fa5619313`; the same patch was verified against the cumulative Modules tree. See `receipt.json`.
