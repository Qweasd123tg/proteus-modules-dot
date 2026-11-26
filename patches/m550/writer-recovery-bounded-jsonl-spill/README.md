# Reuse bounded JSONL replay scratch during writer recovery

The cold writer now uses the shared replay loop with no cut or page boundary.
It folds the same validated records in the same order. JSONL lines crossing a
reader buffer can reuse the existing private spill allocation between records;
the existing 128 KiB retention cap still applies. SQLite keeps using the
existing cursor. The journal format, hashing, repair, and durability are unchanged.

Use `source.patch` on exact Modules commit `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`.
If verified #804 is already applied on that commit (exact tree
`a8a8375f2acb7f9bec37cda297416e4dd1d81207`), extract the alternate from this receipt
and use it instead. Do not apply both. Neither variant is an assertion of
compatibility with an arbitrary base or a cumulative release.

```sh
jq -r '.selection.after_804.patch_base64' receipt.json | base64 -d > source-after-804.patch
```

Exact storage-library suites: stock 104, standalone 105, after #804 106 tests
passed (one existing ignored in each). The new test writes six real inline
JSONL records, checks the shared decoder's scratch retention, and verifies
the real writer's recovered revision, messages, snapshot fingerprint and
unchanged journal bytes. Existing two-engine, damage and ownership tests
run in the suites. No application, worker IPC, runtime, I/O, or RAM benchmark.
The change can keep up to 128 KiB of scratch capacity alive during the fold;
it does not claim lower peak memory.
