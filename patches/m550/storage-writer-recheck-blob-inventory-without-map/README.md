# Recheck recovered writer blobs without a second owned map

After full replay and the same journal stamp check, reuse the existing
inventory matcher instead of materializing a second blob map. The
first map is still retained when approved; otherwise the valid fold
is usable without a trusted head. No filesystem check is removed.

Exact Modules `5377853779ae499b03ff152b97eb1c11eaa64ed2`; full-index apply and reverse verified.
Both unmasked optimized libraries built; 116 scoped tests passed and
one was ignored per arm. Cold typed Resume after hibernation, immediate
repeat and next append agree on JSONL and SQLite. Controls modify,
remove or add a leaf or make the inventory scan reject a non-regular
leaf between replay and recheck; recovery still returns the same fold
and does not publish its optional cached head.

For 128 synthetic inventory leaves, Rust allocation/reallocation calls
on recheck only went 411→265 on JSONL and 411→265 on SQLite.
No application memory, latency, or physical I/O measurement.
