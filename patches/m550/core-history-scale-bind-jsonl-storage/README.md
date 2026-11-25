# Core history-scale: bind the same JSONL worker to the workload and measurement

The generated standalone Core profiles selected no session storage, although resume requires it. Select an executable via `--storage` (default: `proteus-session-storage-module` beside the resolved Core binary). Wire the selected JSONL provider into the peer, parent and private clone profiles. For new synthetic fixtures, the same path goes to the typed seeder only; seed provenance stays separate from the measured reader so one immutable fixture can be reused across two builds.

The subject counters now include samples whose observed executable matches the selected storage worker. Controller scope, sampling policy and memory limits are untouched; this uses the established storage-only benchmark transport budget, not a larger production limit. Compare against runs made with the same revised measurement scope, not older subject numbers that excluded storage.

The checks are local Python/configuration/measurement-contract tests with inert binaries or controlled samples, backed by inspection of the pinned Core launcher and storage worker contracts. No native Proteus resume or quantitative performance change is claimed.

Apply `source.patch` to the pinned Core revision. If #752 is already applied, use the exact alternate in `receipt.json` instead (not both):

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
