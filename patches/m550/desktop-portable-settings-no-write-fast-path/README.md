# Desktop portable: skip write-only setup when settings are already current

The portable launcher invokes a separate Python settings upgrade before starting Desktop. Keep all profile reads, validation and byte comparisons. When nothing needs writing, report the original no-change result without preparing a backup path or importing tempfile on the no-op CLI path (shutil is still imported transitively by argparse in the tested Python). Explicit dry-run, actual restore/upgrade, backups and error reporting retain their existing behavior.

This is a change to the startup helper's no-write path. It is not a measurement of Desktop startup latency or its memory. See the receipt for exact owner and M488 scope and synthetic verification.
