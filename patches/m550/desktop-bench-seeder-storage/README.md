# Desktop history benchmark: use the same JSONL worker for seeding and opening

The benchmark already selects, resolves and hashes one session-storage executable for the run. The compatible Core fixture process previously inherited whatever seed worker its parent environment named, or left selection to PATH. Pass the already selected executable in the seeder child environment, without changing the parent environment, verifier, runtime profile, process measurements or failure handling.

The exact Python runner was exercised against inert subprocesses in five before/after cases: default or explicit worker with an unset or stale environment override, and a failing seeder. The selected path observed by the successful seeder cases now matches the profile and manifest, and the verifier still receives the unchanged ambient environment. The six existing runner tests also passed in each arm.

This is a benchmark input fix, not an application startup or memory improvement. It does not prove binary immutability or support for arbitrary external seed executables. Exact source and scoped lineage are in the receipt.
